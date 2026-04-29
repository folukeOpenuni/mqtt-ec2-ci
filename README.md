# mqtt-ec2-ci

Automated MQTT protocol testing using `pytest` + Docker Compose, with optional infrastructure provisioning via Terraform on AWS EC2.

## Local run (Docker Compose)

Run the broker + test runner locally:

```bash
bash scripts/local-run.sh
```

The JUnit report is written to `reports/results.xml` (this folder is gitignored).

## Run tests without Docker (optional)

```bash
python -m pip install -r <(python -c 'import tomllib; p=tomllib.load(open("pyproject.toml","rb")); print("\\n".join(p["project"]["dependencies"]))')
pytest
```

## Terraform (optional)

The `terraform/` folder provisions:
- An EC2 instance
- A security group allowing SSH (22), MQTT (1883), and MQTT over WebSockets (9001)
- An AWS key pair using your provided **public** SSH key

Required variable:
- `ssh_public_key`: your SSH public key contents (for example from `~/.ssh/id_rsa.pub`)

Example:

```bash
cd terraform
terraform init
terraform apply -var="ssh_public_key=$(cat ~/.ssh/id_rsa.pub)"
```