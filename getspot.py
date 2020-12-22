#!python
import json
import base64
import time
import argparse
from math import ceil
from datetime import datetime
import boto3
import pandas as pd


class EC2Instance(object):
    def __init__(self, config_file):
        with open(config_file, encoding='utf-8') as f:
            self.config = json.load(f)
        self.profile_name = self.config.get('AWSCLI_Profile', 'dev')
        script = self.config.get('User_Data', None)
        if script:
            self.user_data = open("user_data.sh", "rb").read()
        else:
            self.user_data = b'#!/bin/bash\nsudo apt update -y\n'
        self.session = boto3.Session(profile_name=self.profile_name)
        self.client = self.session.client('ec2')
        self.ec2 = self.session.resource('ec2', region_name='eu-west-1')
        self.vpc = list(self.ec2.vpcs.filter(
            Filters=[{'Name': 'tag:Name', 'Values': ['dsci*', 'DSCI*']}]))[0]
        def subnet_name(x): return dict(
            set(t for tags in x.tags for t in list(zip(*tags.items()))))['Name']
        self.subnets = dict([(s.availability_zone, s.id) for s in self.vpc.subnets.all(
        ) if 'public' in subnet_name(s).lower()])
        self.security_group = [x.id for x in self.vpc.security_groups.all() if (
            'http' in x.group_name) & ('ssh' in x.group_name)][0]

    def get_spot_price(self, instance_type):
        response = self.client.describe_spot_price_history(
            InstanceTypes=[instance_type],
            StartTime=datetime.now()
        )
        df = pd.DataFrame(response['SpotPriceHistory'])
        df = df[df.ProductDescription.str.contains("UNIX")]
        df = df.sort_values('SpotPrice').reset_index(drop=True)
        print(df)
        return df

    def request_spot_instance(self, instance_type, price, availability_zone):

        response = self.client.request_spot_instances(
            InstanceCount=1,
            LaunchSpecification={
                "NetworkInterfaces": [
                    {
                        "DeviceIndex": 0,
                        "SubnetId": self.subnets[availability_zone],
                        "Groups": [self.security_group],
                        "AssociatePublicIpAddress": True
                    }
                ],
                'BlockDeviceMappings': [
                    {
                        'DeviceName': '/dev/sda1',
                        'Ebs': {
                            'DeleteOnTermination': True,
                            'VolumeSize': self.config["Volume_Size"],
                            'VolumeType': 'standard'
                        }
                    }
                ],
                'EbsOptimized': True,
                'ImageId': self.config["AMI_Id"],
                'InstanceType': instance_type,
                'KeyName': self.config["Key_Name"],
                'IamInstanceProfile': {'Name': 'EMR_EC2_DefaultRole'},
                'UserData': base64.b64encode(self.user_data).decode("ascii"),
                'Monitoring': {
                    'Enabled': True
                }
            },
            SpotPrice=str(price),
            Type='persistent',
            InstanceInterruptionBehavior='stop'
        )
        return response

    def check_spot_request(self, request_id):
        response = self.client.describe_spot_instance_requests(
            SpotInstanceRequestIds=[
                request_id
            ]
        )
        return response['SpotInstanceRequests'][0]

    def get_spot_instance_id(self, request_id):
        response = self.check_spot_request(request_id)
        if response['Status']['Code'] == 'capacity-not-available':
            return False
        else:
            instance_id = response["InstanceId"] if "InstanceId" in response else None
        return instance_id

    def tag_ec2_instance(self, instance_id):
        response = self.client.create_tags(
            Resources=[
                instance_id,
            ],
            Tags=[
                {
                    "Key": "Project",
                    "Value": self.config["Project"]
                },
                {
                    "Key": "Owner",
                    "Value": self.config["Owner"]
                },
                {
                    "Key": "Name",
                    "Value": self.config["Name"]
                }
            ]
        )
        return response['ResponseMetadata']['HTTPStatusCode'] == 200

    def get_public_ip_address(self, instance_id):
        public_ip = ''
        response = self.client.describe_instances(
            InstanceIds=[instance_id]
        )
        for i in range(5):
            try:
                public_ip = response['Reservations'][0]['Instances'][0]['PublicIpAddress']
                break
            except:
                time.sleep(0.5)
                response = self.client.describe_instances(
                    InstanceIds=[instance_id]
                )
        return public_ip

    def cancel_spot_request(self, request_id):
        canceled = False
        while not canceled:
            response = self.client.cancel_spot_instance_requests(
                SpotInstanceRequestIds=[
                    request_id,
                ]
            )
            canceled = response['ResponseMetadata']['HTTPStatusCode'] == 200
        terminated = False
        while not terminated:
            response = self.check_spot_request(request_id)
            if response['Status']['Code'] == 'request-canceled-and-instance-running':
                response = self.client.terminate_instances(
                    InstanceIds=[response["InstanceId"]]
                )
            terminated = True
        return terminated


if __name__ == "__main__":
    # Parse input param
    parser = argparse.ArgumentParser("get spot instance")
    parser.add_argument("--type", '-t', metavar="type",
                        type=str, default="r4.xlarge",
                        help="select the instance type")
    parser.add_argument("--config", '-c', metavar="config",
                        type=str, default="ec2-dev.json",
                        help="path to config file")
    conf = parser.parse_args()

    instance_type = conf.type
    config_file = conf.config

    ec2 = EC2Instance(config_file)

    # Find cheapest region
    price_df = ec2.get_spot_price(instance_type)
    print("Recommended availibility zone (price):",
          price_df.loc[0, 'AvailabilityZone'], '(', price_df.loc[0, 'SpotPrice'], ')')
    str_idx = input("Enter your preference availibility zone:")
    idx = str(str_idx) if str_idx else 0

    # Request spot instance
    spot_price = str(ceil(float(price_df.loc[0, 'SpotPrice'])*105)/100.0)
    spot_request_response = ec2.request_spot_instance(
        instance_type, spot_price, price_df.loc[0, 'AvailabilityZone'])
    request_id = spot_request_response['SpotInstanceRequests'][0]['SpotInstanceRequestId']
    print("Request_Id:", request_id)

    # Get instance id
    instance_id = None
    while True:
        if instance_id:
            print("Instance_Id", instance_id)
            break
        elif instance_id is not None:
            print("Capacity is not available for spot request. Try other instance type!")
            res = ec2.cancel_spot_request(request_id)
            break
        else:
            time.sleep(1)
            instance_id = ec2.get_spot_instance_id(request_id)

    # Tag instance
    if instance_id:
        tag_response = ec2.tag_ec2_instance(instance_id)
        print("Instance succesfully tagged")

    # Get Instance IP Address
    if instance_id:
        ip = ec2.get_public_ip_address(instance_id)
        print("Public IP Address:", ip, ". Connect using: ")
        print('ssh -i "%s.pem" ubuntu@%s' % (ec2.config["Key_Name"], ip))

    # Menu
    choice = ''
    while instance_id:
        if choice == '1':
            ip = ec2.get_public_ip_address(instance_id)
            print("public IP Address:", ip)
            choice = None
        elif choice == '2':
            print("Instance Type:", instance_type)
            choice = None
        elif choice == '3':
            print("Request Id:", request_id)
            choice = None
        elif choice == '0':
            res = ec2.cancel_spot_request(request_id)
            if res:
                print("Spot instance request canceled")
                break
        else:
            print("\n\n")
            print("=======================================")
            print("1: Shows IP Address")
            print("2: Shows Instance Type")
            print("3: Shows Request Id")
            print("0: Cancel spot instance")
            choice = input("Enter your choice:")
            print("=======================================")
            print("\n\n")
