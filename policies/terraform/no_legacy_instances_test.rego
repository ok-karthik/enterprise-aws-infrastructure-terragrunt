package main

import rego.v1

# PASS: modern instance_type -> no deny
test_modern_instance_type_singular if {
	count(deny) == 0 with input as {
		"resource_changes": [{
			"address": "aws_instance.ok",
			"change": {"actions": ["create"], "after": {"instance_type": "t3.medium"}},
		}],
	}
}

# FAIL: legacy instance_type (singular field) -> deny fires
test_legacy_instance_type_singular if {
	count(deny) > 0 with input as {
		"resource_changes": [{
			"address": "aws_instance.bad",
			"change": {"actions": ["create"], "after": {"instance_type": "t2.micro"}},
		}],
	}
}

# PASS: modern instance_types (list field, e.g. EKS node group) -> no deny
test_modern_instance_types_list if {
	count(deny) == 0 with input as {
		"resource_changes": [{
			"address": "aws_eks_node_group.ok",
			"change": {"actions": ["create"], "after": {"instance_types": ["t4g.small", "m5.large"]}},
		}],
	}
}

# FAIL: legacy instance_types (list field) -> deny fires
test_legacy_instance_types_list if {
	count(deny) > 0 with input as {
		"resource_changes": [{
			"address": "aws_eks_node_group.bad",
			"change": {"actions": ["create"], "after": {"instance_types": ["m4.large"]}},
		}],
	}
}
