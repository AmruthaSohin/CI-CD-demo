import logging
import json
from typing import Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

class S3BucketTagger:
    def __init__(self, region_name: str = "us-east-1", profile_name: str | None = None) -> None:
        try:
            if profile_name:
                session = boto3.Session(profile_name=profile_name)
                self.s3_client = session.client("s3", region_name=region_name)
            else:
                self.s3_client = boto3.client("s3", region_name=region_name)
            self.region_name = region_name
            self.profile_name = profile_name
            self._setup_logging()
        except NoCredentialsError as e:
            self.logger.error("AWS credentials not found")
            raise e

    def _setup_logging(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)

    def list_buckets(self) -> list[dict[str, Any]]:
        try:
            response = self.s3_client.list_buckets()
            buckets = response.get("Buckets", [])
            self.logger.info(f"Found {len(buckets)} buckets in account")
            return buckets
        except ClientError as e:
            self.logger.error(f"Failed to list buckets: {e}")
            raise

    def get_bucket_tags(self, bucket_name: str) -> dict[str, str]:
        try:
            response = self.s3_client.get_bucket_tagging(Bucket=bucket_name)
            tag_set = response.get("TagSet", [])
            return {tag["Key"]: tag["Value"] for tag in tag_set}
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchTagSet":
                self.logger.info(f"No existing tags found for bucket: {bucket_name}")
                return {}
            self.logger.error(f"Failed to fetch tags for bucket {bucket_name}: {e}")
            raise

    def backup_tags(self, bucket_name: str, tags: dict[str, str]) -> None:
        filename = f"{bucket_name}_tags_backup.json"
        try:
            with open(filename, "w") as f:
                json.dump(tags, f, indent=4)
            self.logger.info(f"Backed up existing tags for {bucket_name} to {filename}")
        except Exception as e:
            self.logger.error(f"Failed to back up tags for {bucket_name}: {e}")

    def apply_tags_to_bucket(
        self,
        bucket_name: str,
        tags: dict[str, str],
        merge_existing: bool = True,
        dry_run: bool = False,
    ) -> bool:
        try:
            filtered_tags = {k: v for k, v in tags.items() if v.strip()}
            if len(filtered_tags) != len(tags):
                removed_count = len(tags) - len(filtered_tags)
                self.logger.info(f"Filtered out {removed_count} empty tag values")

            existing_tags = self.get_bucket_tags(bucket_name)
            self.backup_tags(bucket_name, existing_tags)  # 🔐 Backup step

            if merge_existing:
                final_tags = {**existing_tags, **filtered_tags}
                self.logger.info(
                    f"Merging {len(filtered_tags)} new tags with {len(existing_tags)} existing tags"
                )
            else:
                final_tags = filtered_tags
                self.logger.info(f"Replacing all tags with {len(filtered_tags)} new tags")

            tag_set = [{"Key": k, "Value": v} for k, v in final_tags.items()]

            if dry_run:
                self.logger.info(
                    f"Dry run: This would apply tags to {bucket_name}: {final_tags}"
                )
                return True

            self.s3_client.put_bucket_tagging(
                Bucket=bucket_name, Tagging={"TagSet": tag_set}
            )

            self.logger.info(
                f"Successfully applied {len(final_tags)} tags to bucket: {bucket_name}"
            )
            return True

        except ClientError as e:
            self.logger.error(f"Failed to apply tags to {bucket_name}: {e}")
            return False

    def tag_all_bucket(
        self,
        tags: dict[str, str],
        merge_existing: bool = True,
        dry_run: bool = False,
        bucket_filter: str | None = None,
    ) -> dict[str, bool]:

        buckets = self.list_buckets()
        results = {}

        filtered_buckets = [
            bucket for bucket in buckets if not bucket_filter or bucket_filter in bucket["Name"]
        ]

        if bucket_filter:
            self.logger.info(
                f"Filtered to {len(filtered_buckets)} buckets matching '{bucket_filter}'"
            )

        for bucket in filtered_buckets:
            bucket_name = bucket["Name"]
            success = self.apply_tags_to_bucket(
                bucket_name, tags, merge_existing, dry_run
            )
            results[bucket_name] = success

        successful = sum(results.values())
        total = len(results)
        self.logger.info(
            f"Activity Completed: {successful}/{total}"
        )

        return results

    def remove_tags_from_bucket(
        self, bucket_name: str, tag_keys: list[str], dry_run: bool = False
    ) -> bool:
        try:
            existing_tags = self.get_bucket_tags(bucket_name)

            if not existing_tags:
                self.logger.info(f"No tags to remove from: {bucket_name}")
                return True

            remaining_tags = {
                k: v for k, v in existing_tags.items() if k not in tag_keys
            }

            if dry_run:
                removed_keys = [k for k in tag_keys if k in existing_tags]
                self.logger.info(
                    f"Dry run: Would remove tags {removed_keys} from {bucket_name}"
                )
                return True

            if remaining_tags:
                tag_set = [{"Key": k, "Value": v} for k, v in remaining_tags.items()]
                self.s3_client.put_bucket_tagging(
                    Bucket=bucket_name, Tagging={"TagSet": tag_set}
                )
            else:
                self.s3_client.delete_bucket_tagging(Bucket=bucket_name)

            removed_count = len([k for k in tag_keys if k in existing_tags])
            self.logger.info(
                f"Removed {removed_count} tags from bucket: {bucket_name}"
            )
            return True

        except ClientError as e:
            self.logger.error(f"Failed to remove tags from {bucket_name}: {e}")
            return False

def main() -> None:
    tagger = S3BucketTagger(profile_name=profile_name)  # 🧑‍💻 Use dev profile if needed
    standard_tags = {
        "Env": "dev",
        "owner": "devowner@example.com",
        "Project": "my-dev-project",
        "CostCenter": "456",
        "BusinessUnit": "Marketing",
        "BusinessSegment": "Digital",
        "LeanIXID": "abc-12345"
    }

    print("List all buckets")
    buckets = tagger.list_buckets()
    for bucket in buckets:
        print(f"Bucket: {bucket['Name']} (Created: {bucket['CreationDate']})")

    print("\n===Tagging Buckets in Dev===")
    tagger.tag_all_bucket(standard_tags, dry_run=False)

if __name__ == "__main__":
    main()
