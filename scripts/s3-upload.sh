#!/bin/bash 
# 
# This is author's script for uploading lambda function. 
# If you want to deploy customized lambda to your environment, use scripts/deploy.sh
# 

set -xue

pip install -r ../requirements.txt -t ../function

aws cloudformation package --template ../template.yaml \
    --s3-bucket tokyo.k.iwami --s3-prefix cost-watcher-public --output-template-file ../packaged.yaml

aws s3 cp ../packaged.yaml s3://tokyo.k.iwami/cost-watcher-public/

# grant public-read permissions to all objects in tokyo.k.iwami/cost-watcher-public.
aws s3 ls --recursive s3://tokyo.k.iwami/cost-watcher-public | awk '{print $4}' \
    | xargs -I{} aws s3api put-object-acl --acl public-read --bucket tokyo.k.iwami --key "{}"