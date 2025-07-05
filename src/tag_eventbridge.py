#!/usr/bin/env python3
import time
import random
import os
import logging
from typing import Dict, List, Any
import json
import boto3
from botocore.exceptions import ClientError, BotoCoreError

class EventBridgeTagger:
    def __init__(self, session: boto3.session):
        self.events_client = session.client('events')
        self.session = session

    def _wait_with_jitter(self, base_delay: float = 0.5) -> None:
        jitter = random.uniform(0.1, 0.5)
        time.sleep(base_delay + jitter)
    
    def list_rules_by_pattern(self, name_patterns: List[str]) -> List[Dict[str, Any]]:
        try:
            matched_rules = []
            paginator = self.events_client.get_paginator('list_rules')

            for page in paginator.paginate():
                for rule in page.get('Rules', []):
                    rule_name = rule['Name']
                    rule_arn = rule['Arn']

                    if any(pattern in rule_name for pattern in name_patterns):
                        try:
                            tag_response = self.events_client.list_tags_for_resource(ResourceARN=rule_arn)
                            current_tags = {tag['Key']: tag['Value'] for tag in tag_response.get('Tags', [])}

                            matched_rules.append({
                                'name': rule_name,
                                'arn': rule_arn,
                                'current_tags': current_tags
                            })

                        except ClientError as e:
                            if e.response['Error']['Code'] == 'UnsupportedOperation':
                                print(f"Taging not supported for {rule_name}")
                            else:
                                print(f"Warning: Could not get tags for rule {rule_name}: {e}")
                            matched_rules.append({
                                'name': rule_name,
                                'arn': rule_arn,
                                'current_tags': {},
                                'tagging_supported': False
                            })    
                        self._wait_with_jitter()
            return matched_rules
        except (ClientError, BotoCoreError) as e:
            print(f"Error listing EventBridge rules: {e}")
            return []
        
    def show_tag_diff(self, rule_name: str, current_tags: Dict[str, str], new_tags: Dict[str, str], tagging_supported: bool = True) -> None:
        print(f"\n--- {rule_name} ---")

        if not tagging_supported:
            print("Not supported")
            return
        all_keys = set(current_tags.keys()) | set(new_tags.keys())
        has_changes = False

        for key in sorted(all_keys):
            current_value = current_tags.get(key)
            new_value = new_tags.get(key)

            if current_value is None and new_value is not None:
                print(f"+ {key}: {new_value}")
                has_changes = True
            elif current_value is not None and new_value is None:
                print(f"- {key}: {current_value}")
                has_changes = True
            elif current_value != new_value:
                print(f"~ {key}: {current_value} -> {new_value}")
                has_changes = True
        
        if not has_changes:
            print("No changes required")

    def apply_tags(self, rule_arn: str, rule_name: str, tags: Dict[str, str]) -> bool:
        try:
            tag_list = [{'Key': k, 'Value': v} for k, v in tags.items()]
            self.events_client.tag_resource(
                ResourceARN=rule_arn,
                Tags=tag_list
            )

            print(f"Successfully tagged {rule_name}")
            self._wait_with_jitter()
            return True
        
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDeniedException':
                print(f"Access Denied {rule_name}: {e}")
            elif error_code == 'ResourceNotFound':
                print(f"Rule not found {rule_name}: {e}")
            elif error_code == 'unsupported ':
                print(f"Tagging not supported for {rule_name}")
            elif error_code == 'ThrottlingExcep':
                print(f"Rate limit exceed for {rule_name}, retrying")
                time.sleep(2)
                return self.apply_tags(rule_arn, rule_name, tags)
            else:
                print(f"Error tagging rule {rule_name}: {e}")
            return False
        except Exception as e:
            print(f"Enexcepted Error {rule_name}: {e}")
            return False
        
    def tag_rules(self, name_patterns: List[str], tags: Dict[str,str]) -> None:
        print("Tagging")

        rules = self.list_rules_by_pattern(name_patterns)

        if not rules:
            print("No Match")
            return
        taggable_rules = [rule for rule in rules if rule.get('tagging_supported', True)]

        print(f"Found{len(rules)} matching rules")
        print(f"Taggable: {len(taggable_rules)}")
        print(f"Not: {len(rules) - len(taggable_rules)}")

        for rule in rules:
            current_tags = rule['current_tags']
            merged_tags = {**current_tags, **tags}
            tagging_supported = rule.get('tagging_supported', True)
            self.show_tag_diff(rule['name'], current_tags, merged_tags, tagging_supported)

        if not taggable_rules:
            print("No taggable rule found")
            return
        

        is_ci = os.getenv("CI") == "true"

        if is_ci or input(f"\nProceed with tagging {len(taggable_rules)} ?(yes/No)").strip().lower() == "yes":
            self.apply_tags(taggable_rules, tags)
        else:
            print("Tagging aborted by user.")

       # response = input(f"\nProceed with tagging {len(taggable_rules)} ?(yes/No)").strip().lower()

        if response != 'yes':
            print("Tagging cancelled")
            return
        
        success_count = 0
        for rule in taggable_rules:
            current_tags = rule['current_tags']
            merged_tags = {**current_tags, **tags}

            if self.apply_tags(rule['arn'], rule['name'], merged_tags):
                success_count += 1

        print(f"\n Completed: {success_count}/{len(taggable_rules)} rules tagged successfully")


def main():
   # PROFILE = 'prd'
    REGION = "us-east-1"

    tags = {
        "Project": "abc",
        "Env": "prd",
        "owner": "pqr"
    }

    name_patterns = ["test", "nex", "project"]

    # session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    # session = boto3.Session(profile_name=profile_name, region_name=REGION)
    session = boto3.Session(region_name=REGION)
    tagger = EventBridgeTagger(session)

    tagger.tag_rules(name_patterns, tags)

if __name__ == "__main__":
    main()


        
