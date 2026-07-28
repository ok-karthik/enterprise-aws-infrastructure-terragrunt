# compute/eks

Reusable EKS module wrapping `terraform-aws-modules/eks/aws`. Encrypts Kubernetes secrets with a dedicated KMS key and enables full control-plane logging (api, audit, authenticator, controllerManager, scheduler) by default, so clusters are auditable and encrypted at rest out of the box.

## Inputs

| Name | Description | Type | Default |
| :--- | :--- | :--- | :--- |
| `cluster_name` | Name of the EKS cluster | `string` | n/a |
| `kubernetes_version` | Kubernetes version to use | `string` | `"1.30"` |
| `vpc_id` | VPC ID where the cluster will be deployed | `string` | n/a |
| `subnet_ids` | A list of subnet IDs where the EKS nodes will be deployed | `list(string)` | n/a |
| `min_size` | Minimum number of nodes | `number` | `1` |
| `max_size` | Maximum number of nodes | `number` | `3` |
| `desired_size` | Desired number of nodes | `number` | `1` |
| `instance_types` | List of instance types for the node group | `list(string)` | `["t4g.small", "t4g.medium"]` |
| `tags` | A map of tags to add to all resources | `map(string)` | `{}` |

## Outputs

| Name | Description |
| :--- | :--- |
| `cluster_arn` | The Amazon Resource Name (ARN) of the cluster |
| `cluster_certificate_authority_data` | Base64 encoded certificate data required to communicate with the cluster |
| `cluster_endpoint` | Endpoint for your Kubernetes API server |
| `cluster_id` | The name of the EKS cluster. Works for both existing and new clusters |
| `cluster_name` | The name of the EKS cluster |
| `oidc_provider_arn` | The ARN of the OIDC Provider if `enable_irsa = true` |
