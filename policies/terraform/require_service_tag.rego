package main

# Rego Lesson: The "deny" rule
# In Rego, we define what is WRONG. If this rule is true, the test fails.
# 'input' is the JSON representation of our Terraform Plan.

mandatory_tags = ["Service", "Environment", "Project"]

deny[msg] {
    # 1. Find every resource change in the plan
    resource := input.resource_changes[_]
    
    # 2. We only care about resources being created (+) or updated (~)
    # We skip resources being deleted (-)
    actions := resource.change.actions
    count({a | actions[a]; a == "create" or a == "update"}) > 0

    # 3. Check the tags after the change
    actual_tags := resource.change.after.tags
    
    # 4. Loop through our mandatory list and find any that are missing
    tag := mandatory_tags[_]
    not actual_tags[tag]
    
    # 5. Create the error message
    msg := sprintf("Governance Violation: Resource '%v' is missing the mandatory '%v' tag.", [resource.address, tag])
}
