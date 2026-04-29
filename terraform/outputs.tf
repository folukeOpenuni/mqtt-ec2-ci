output "ec2_public_ip" {
  description = "Public IP of the MQTT test runner EC2 instance"
  value       = aws_instance.mqtt_test_runner.public_ip
}

output "ec2_instance_id" {
  description = "Instance ID of the test runner"
  value       = aws_instance.mqtt_test_runner.id
}

output "mqtt_broker_endpoint" {
  description = "MQTT broker endpoint (port 1883)"
  value       = "${aws_instance.mqtt_test_runner.public_ip}:1883"
}