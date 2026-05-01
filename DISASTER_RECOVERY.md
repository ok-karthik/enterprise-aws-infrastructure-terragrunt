# 🚑 Disaster Recovery & Failure Modes

In an enterprise Infrastructure-as-Code (IaC) environment, failures happen. This document explicitly outlines our philosophy on handling failed deployments, state corruption, and rollback strategies.

## 1. The Rollback Philosophy: "Roll-Forward"

**Question:** *What is our rollback strategy if a deployment fails or breaks the environment?*

**Answer:** **We do NOT "Rollback." We Roll-Forward.**

In traditional software, rolling back is as simple as deploying the previous artifact. In Terraform/Terragrunt, attempting to revert a commit after a partial or failed deployment forces Terraform to attempt to destroy newly (or partially) created resources. This often results in a catastrophic failure loop, as AWS APIs may not allow the destruction of resources that are stuck in a transitioning state.

### The Roll-Forward Procedure
1. **Identify the Failure:** Read the CI/CD pipeline logs to find the exact AWS API error (e.g., "Timeout waiting for EKS cluster", "IAM Role already exists").
2. **Fix the Code:** Push a new commit to the PR that corrects the issue.
3. **Re-Apply:** Allow the pipeline to run the updated plan. Terraform's declarative nature will automatically reconcile the partial state with the new desired state.

## 2. Failure Mode: "Apply Fails Halfway"

**Question:** *What happens to the infrastructure and state if `terragrunt apply` times out or fails halfway through?*

**Answer:**
Because we use **S3 backend with DynamoDB locking**, the state is protected.
1. When the apply starts, Terragrunt acquires a lock in DynamoDB.
2. If the apply fails halfway, Terraform writes the *partial* state of the successfully created resources to S3 before exiting.
3. The lock is released.
4. The infrastructure is now in a "partial" state, but the **state file accurately reflects this reality**.
5. The next `terragrunt plan` will read the partial state and simply pick up where it left off.

## 3. Handling Locked State Files

Occasionally, a catastrophic runner crash (e.g., GitHub Actions terminating abruptly) will prevent Terraform from releasing the DynamoDB lock.

**Symptom:** `Error acquiring the state lock... Lock Info: ID: 1234-5678...`

**Resolution (Break the Lock):**
1. Copy the Lock ID from the error message.
2. Authenticate locally with the AWS CLI.
3. Run the force-unlock command:
   ```bash
   terragrunt force-unlock <LOCK_ID>
   ```
*(Note: Only execute this if you are 100% certain the pipeline runner has been terminated and no other process is actively mutating the state).*

## 4. State Corruption & Disasters

If the state file becomes corrupted (highly unlikely due to Terraform's atomic writes, but possible in extreme edge cases):

1. **S3 Versioning:** Our S3 state buckets have **versioning strictly enabled**.
2. **Recovery:**
   - Navigate to the S3 bucket in the AWS Console.
   - Find the specific `.tfstate` file.
   - Delete the current corrupted version to immediately restore the previous known-good version.
3. **Manual Reconciliation:** If resources were created *after* the restored version, you must use `terragrunt import` to bring them back into the state file to prevent Terraform from trying to recreate them.

## 5. Manual State Manipulation (Surgical Strikes)

Sometimes, AWS resources get stuck in a "deleting" state, or someone manually deletes a resource via the console (causing drift). If Terraform is blocked:

**Remove the resource from state:**
```bash
terragrunt state rm module.eks.aws_eks_cluster.this[0]
```
This tells Terraform to "forget" about the resource. The next `apply` will attempt to create it from scratch.

---

> **Summary:** Trust the declarative engine. Protect the state. Fix the code. **Roll-Forward.**
