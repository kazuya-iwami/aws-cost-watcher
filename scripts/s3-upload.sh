#!/bin/bash 
set -xue

pip install -r ../requirements.txt -t ../function

(cd ../function; zip -r9 ../function.zip .)

# Upload files
aws s3 cp ../function.zip s3://tokyo.k.iwami/cost-watcher/
aws s3 cp ../template.yaml s3://tokyo.k.iwami/cost-watcher/
