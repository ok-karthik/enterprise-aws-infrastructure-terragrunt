package main

# Rego V1: The modern standard
import rego.v1

legacy_instance_prefixes := ["t2.", "m3.", "m4.", "c3.", "c4."]

deny contains msg if {
    # 1. Look for compute resources
    resource := input.resource_changes[_]
    
    # 2. Extract the instance type(s)
    # This now returns a set, which we iterate over using [_]
    instance_type := get_instance_types(resource)[_]
    
    # 3. Check if it matches our 'Legacy' list
    some prefix in legacy_instance_prefixes
    startswith(instance_type, prefix)
    
    # 4. Success! (Wait, 'deny' success means a policy violation)
    msg := sprintf("Governance Violation: Resource '%v' is using an old-generation instance type (%v). Modernize to Nitro-based instances (e.g., t3, m5) for better performance and cost.", [resource.address, instance_type])
}

# Helper to always return a SET of types (even if only 1 string exists)
# This uses the 'else' pattern to handle different Terraform schemas safely in V1
get_instance_types(res) := types if {
    res.change.after.instance_types
    types := {t | t := res.change.after.instance_types[_]}
} else := types if {
    res.change.after.instance_type
    types := {res.change.after.instance_type}
} else := {}
