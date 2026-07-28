# network/vpc

Reusable VPC module wrapping `terraform-aws-modules/vpc/aws`. Ships hardened by default: a deny-all default network ACL, a black-hole default security group (no ingress/egress), and VPC Flow Logs shipped to CloudWatch — so a caller cannot accidentally get an open-by-default network.

## Inputs

| Name | Description | Type | Default |
| :--- | :--- | :--- | :--- |
| `name` | Name to be used on all resources as prefix | `string` | n/a |
| `cidr` | The CIDR block for the VPC | `string` | n/a |
| `azs` | A list of availability zones names or ids in the region | `list(string)` | n/a |
| `private_subnets` | A list of private subnets inside the VPC | `list(string)` | n/a |
| `public_subnets` | A list of public subnets inside the VPC | `list(string)` | n/a |
| `enable_nat_gateway` | Should be true if you want to provision NAT Gateways for each of your private networks | `bool` | `true` |
| `single_nat_gateway` | Should be true if you want to provision a single shared NAT Gateway across all of your private networks | `bool` | `true` |
| `cluster_name` | Name of the EKS cluster to tag subnets for | `string` | `""` |
| `tags` | A map of tags to add to all resources | `map(string)` | `{}` |

## Outputs

| Name | Description |
| :--- | :--- |
| `vpc_id` | The ID of the VPC |
| `private_subnets` | List of IDs of private subnets |
| `public_subnets` | List of IDs of public subnets |
| `nat_public_ips` | List of public Elastic IP addresses created for HTTP Load Balancing |
| `vpc_cidr_block` | The CIDR block of the VPC |
