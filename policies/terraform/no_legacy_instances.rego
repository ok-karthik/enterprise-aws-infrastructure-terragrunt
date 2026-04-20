package main

# Rego Lesson: Functions and Multiple Definitions
# In Rego, we can define a function multiple times. 
# It acts like an 'OR'—the engine will try every definition until one works!

legacy_instance_prefixes = ["t2.", "m3.", "m4.", "c3.", "c4."]

deny[msg] {
    # 1. Look for compute resources
    resource := input.resource_changes[_]
    
    # 2. Extract the instance type regardless of the resource type
    instance_type := get_instance_type(resource)
    
    # 3. Check if it matches our 'Legacy' list
    prefix := legacy_instance_prefixes[_]
    startswith(instance_type, prefix)
    
    # 4. Success! (Wait, 'deny' success means a policy violation)
    msg := sprintf("Governance Violation: Resource '%v' is using an old-generation instance type (%v). Modernize to Nitro-based instances (e.g., t3, m5) for better performance and cost.", [resource.address, instance_type])
}

# Functions to handle different Terraform resource schemas
get_instance_type(res) = val {
    # Handle EKS Node Groups (Uses 'instance_types' list)
    val := res.change.after.instance_types[_]
}

get_instance_type(res) = val {
    # Handle standard EC2 Instances (Uses 'instance_type' string)
    val := res.change.after.instance_type
}
