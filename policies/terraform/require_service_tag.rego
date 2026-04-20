package main

# Rego V1: The modern standard
import rego.v1

mandatory_tags := ["Service", "Environment", "Project"]

deny contains msg if {
    # 1. Find every resource change in the plan
    resource := input.resource_changes[_]
    
    # 2. We only care about resources being created (+) or updated (~)
    # Using 'some' for explicit iteration in V1
    some action in resource.change.actions
    action in ["create", "update"]

    # 3. Check the tags after the change (looking at 'tags_all' for inherited provider tags)
    actual_tags := object.get(resource.change.after, "tags_all", resource.change.after.tags)
    
    # 4. Check for missing mandatory tags
    some tag in mandatory_tags
    not actual_tags[tag]
    
    # 5. Create the error message
    msg := sprintf("Governance Violation: Resource '%v' is missing the mandatory '%v' tag (checked in tags_all).", [resource.address, tag])
}
