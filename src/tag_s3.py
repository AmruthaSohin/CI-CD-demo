import boto3
import os
import logging

# Best practice: logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# Best practice: use session with environment credentials
session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    aws_session_token=os.getenv("AWS_SESSION_TOKEN", None),
    region_name="us-east-1"  # Change if your buckets are region-specific
)

s3 = session.client('s3')

# Define tags to apply
REQUIRED_TAGS = {
    "project": "prod",
    "costcenter": "engineering",
    "owner": "abc@gmail.com"
}

def get_existing_tags(bucket_name):
    try:
        tagging = s3.get_bucket_tagging(Bucket=bucket_name)
        return {tag['Key']: tag['Value'] for tag in tagging['TagSet']}
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchTagSet':
            return {}
        else:
            raise

def apply_tags(bucket_name):
    existing_tags = get_existing_tags(bucket_name)
    updated_tags = {**existing_tags, **REQUIRED_TAGS}

    tag_set = [{"Key": k, "Value": v} for k, v in updated_tags.items()]
    response = s3.put_bucket_tagging(
        Bucket=bucket_name,
        Tagging={'TagSet': tag_set}
    )
    logger.info(f"Tagged bucket: {bucket_name} with {REQUIRED_TAGS}")

def main():
    buckets = s3.list_buckets()['Buckets']
    for bucket in buckets:
        bucket_name = bucket['Name']
        try:
            apply_tags(bucket_name)
        except Exception as e:
            logger.error(f"Error tagging bucket {bucket_name}: {e}")

if __name__ == "__main__":
    main()
