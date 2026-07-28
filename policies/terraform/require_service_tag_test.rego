package main

import rego.v1

# PASS: resource created with all mandatory tags in tags_all -> no deny
test_service_tag_present if {
	count(deny) == 0 with input as {
		"resource_changes": [{
			"address": "aws_s3_bucket.ok",
			"change": {
				"actions": ["create"],
				"after": {"tags_all": {"Service": "net", "Environment": "Dev", "Project": "x"}},
			},
		}],
	}
}

# FAIL: resource created missing the Service tag -> deny fires
# NOTE: "tags" must be present alongside "tags_all" (as in real Terraform plan
# JSON) because the rule's object.get(..., resource.change.after.tags) default
# argument is eagerly evaluated and errors out if "tags" is absent entirely.
test_service_tag_missing if {
	count(deny) > 0 with input as {
		"resource_changes": [{
			"address": "aws_s3_bucket.bad",
			"change": {
				"actions": ["create"],
				"after": {
					"tags": {"Environment": "Dev", "Project": "x"},
					"tags_all": {"Environment": "Dev", "Project": "x"},
				},
			},
		}],
	}
}

# FAIL: resource updated missing the Project tag -> deny fires
test_service_tag_missing_on_update if {
	count(deny) > 0 with input as {
		"resource_changes": [{
			"address": "aws_s3_bucket.bad_update",
			"change": {
				"actions": ["update"],
				"after": {
					"tags": {"Service": "net", "Environment": "Dev"},
					"tags_all": {"Service": "net", "Environment": "Dev"},
				},
			},
		}],
	}
}

# PASS: resource with no create/update action (e.g. no-op) is ignored regardless of tags
test_service_tag_ignored_for_no_op if {
	count(deny) == 0 with input as {
		"resource_changes": [{
			"address": "aws_s3_bucket.noop",
			"change": {
				"actions": ["no-op"],
				"after": {"tags_all": {}},
			},
		}],
	}
}
