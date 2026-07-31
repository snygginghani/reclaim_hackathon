#!/usr/bin/env bash
# Removes everything the demo deployment created. Safe to run twice.
# Does NOT touch the apex/www/coaster CloudFront records.
set -u

INSTANCE_ID=i-09c29e4b90a2d341c
SG_ID=sg-0e423a48c8cfaf1ea
ZONE_ID=Z02631813GSS0A97XPP4D
IP=18.209.237.17

echo "terminating instance $INSTANCE_ID (its 20GB EBS volume is delete-on-termination)"
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --query 'TerminatingInstances[0].CurrentState.Name' --output text

echo "removing DNS record lore.archbyhusam.click"
aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" --change-batch "{
  \"Changes\": [{\"Action\": \"DELETE\", \"ResourceRecordSet\": {
    \"Name\": \"lore.archbyhusam.click\", \"Type\": \"A\", \"TTL\": 60,
    \"ResourceRecords\": [{\"Value\": \"$IP\"}]}}]}" \
  --query 'ChangeInfo.Status' --output text

echo "waiting for termination before releasing the security group"
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
aws ec2 delete-security-group --group-id "$SG_ID" && echo "security group deleted"
aws ec2 delete-key-pair --key-name lore-demo && echo "key pair deleted"

echo "done — no further charges"
