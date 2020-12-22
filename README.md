# Tools for Spin Up Spot Instance
## How to use?
1. Please modify the json configuration file according to your usage. Example:
```javascript
{
    "Name": "Septian-spot",
    "Project": "PurchaseInvoice",
    "Owner": "septian-putra@hotmail.com",
    "Key_Name": "septian-irl",
    "Volume_Size": 300,
    "AMI_Id" : "ami-0c1c86015faf25d24",
    "AWSCLI_Profile": "default",
    "User_Data": "user_data.sh"
}
```
2. Modify the user_data.sh bootstrapping script if necessary. Example:
```bash
#!/bin/bash
sudo apt update -y
sudo apt install gcc htop awscli python3-pip -y
rm -rf /home/ubuntu/purchase-invoice
echo "Checking if anaconda3 path exists..."
FILE=anaconda3/envs
cd /home/ubuntu/
if [ -d "$FILE" ]; then
    echo "$FILE exists!"
    echo "Activating Conda Environment..."
    su -c "source /home/ubuntu/anaconda3/etc/profile.d/conda.sh; conda init bash; conda activate tensorflow2_p36;\
    conda info -e; conda list; conda update --all -y;\
    python -m pip install boto3 boto pandas matplotlib seaborn gensim pyarrow scikit-learn joblib;\
    python -m pip install GitPython mlflow;\
    pip3 install jupyterlab jupyter_contrib_nbextensions memory_profiler;\
    nohup jupyter lab --ip=0.0.0.0 --no-browser --port=8888 --allow-root &" ubuntu
else
    echo "$FILE does not exist!"
fi

```
3. In windows run `python getspot.py -t <instance-type> -c <json-config-path>`
For this project you can use `r4.8xlarge` for CPU instance or `g3.8xlarge` for GPU instance.
For the jupyterlab, fill with no password.

## Check Bootstraping Status
`vi /var/log/cloud-init-output.log`
