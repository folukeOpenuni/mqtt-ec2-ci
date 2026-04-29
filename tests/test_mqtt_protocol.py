"""
MQTT Protocol Test Suite
========================
Automated tests validating MQTT protocol behaviour against a live broker.

Test areas covered:
  - Basic connectivity (CONNECT / DISCONNECT)
  - Publish / Subscribe (QoS 0, 1, 2)
  - Retained messages
  - Last Will & Testament (LWT)
  - Topic wildcards (+ and #)
  - Payload integrity
  - Message ordering
"""

import os
import json
import time
import threading
import paho.mqtt.client as mqtt

# ── Configuration ─────────────────────────────────────────────────────────────

BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))
CONNECT_TIMEOUT = 5
MESSAGE_TIMEOUT = 5
BASE_TOPIC = "ci/test"


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_client(client_id: str) -> mqtt.Client:
    """Create and return a connected MQTT client."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    return client


def subscribe_and_collect(
    topic: str,
    qos: int = 0,
    expected_count: int = 1,
    timeout: float = MESSAGE_TIMEOUT,
    client_id: str = "sub-collector",
) -> list[dict]:
    """Subscribe to a topic and collect messages until expected_count or timeout."""
    received: list[dict] = []
    done = threading.Event()

    def on_message(client, userdata, msg):
        received.append(
            {
                "topic": msg.topic,
                "payload": msg.payload.decode("utf-8"),
                "qos": msg.qos,
                "retain": msg.retain,
            }
        )
        if len(received) >= expected_count:
            done.set()

    client = make_client(client_id)
    client.on_message = on_message
    client.subscribe(topic, qos)
    done.wait(timeout=timeout)
    client.loop_stop()
    client.disconnect()
    return received


# ── Tests: Connectivity ───────────────────────────────────────────────────────


class TestConnectivity:
    def test_connect_and_disconnect(self):
        """TC-CON-01: Client can connect and cleanly disconnect."""
        connected = threading.Event()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="tc-con-01")

        def on_connect(cl, ud, flags, rc, properties=None):
            connected.set()

        client.on_connect = on_connect
        client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
        client.loop_start()
        assert connected.wait(timeout=CONNECT_TIMEOUT), (
            "Broker did not acknowledge CONNECT"
        )
        client.loop_stop()
        client.disconnect()

    def test_multiple_concurrent_connections(self):
        """TC-CON-02: Broker accepts multiple simultaneous clients."""
        clients, events = [], []

        for i in range(5):
            ev = threading.Event()
            cl = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2, client_id=f"tc-con-02-{i}"
            )
            cl.on_connect = lambda c, u, f, rc, props, ev=ev: ev.set()
            cl.connect(BROKER_HOST, BROKER_PORT)
            cl.loop_start()
            clients.append(cl)
            events.append(ev)

        for ev in events:
            assert ev.wait(timeout=CONNECT_TIMEOUT), "A client failed to connect"

        for cl in clients:
            cl.loop_stop()
            cl.disconnect()


# ── Tests: Publish / Subscribe ────────────────────────────────────────────────


class TestPublishSubscribe:
    def test_qos0_message_delivery(self):
        """TC-PS-01: Message published at QoS 0 is received by subscriber."""
        topic, payload = f"{BASE_TOPIC}/qos0", "hello-qos0"
        received, done = [], threading.Event()
        sub = make_client("tc-ps-01-sub")

        def on_msg(client, ud, msg):
            received.append(msg.payload.decode())
            done.set()

        sub.on_message = on_msg
        sub.subscribe(topic, qos=0)
        time.sleep(0.2)

        pub = make_client("tc-ps-01-pub")
        pub.publish(topic, payload, qos=0)

        assert done.wait(timeout=MESSAGE_TIMEOUT), "QoS 0 message not received"
        assert received[0] == payload

        for c in (sub, pub):
            c.loop_stop()
            c.disconnect()

    def test_qos1_message_delivery(self):
        """TC-PS-02: Message published at QoS 1 is received and acknowledged."""
        topic, payload = f"{BASE_TOPIC}/qos1", "hello-qos1"
        received, done = [], threading.Event()
        sub = make_client("tc-ps-02-sub")

        def on_msg(client, ud, msg):
            received.append({"payload": msg.payload.decode(), "qos": msg.qos})
            done.set()

        sub.on_message = on_msg
        sub.subscribe(topic, qos=1)
        time.sleep(0.2)

        pub = make_client("tc-ps-02-pub")
        result = pub.publish(topic, payload, qos=1)
        result.wait_for_publish(timeout=MESSAGE_TIMEOUT)

        assert done.wait(timeout=MESSAGE_TIMEOUT), "QoS 1 message not received"
        assert received[0]["payload"] == payload

        for c in (sub, pub):
            c.loop_stop()
            c.disconnect()

    def test_qos2_exactly_once_delivery(self):
        """TC-PS-03: Message published at QoS 2 is received exactly once."""
        topic, payload = f"{BASE_TOPIC}/qos2", "hello-qos2"
        received, done = [], threading.Event()
        sub = make_client("tc-ps-03-sub")

        def on_msg(client, ud, msg):
            received.append(msg.payload.decode())
            done.set()

        sub.on_message = on_msg
        sub.subscribe(topic, qos=2)
        time.sleep(0.2)

        pub = make_client("tc-ps-03-pub")
        result = pub.publish(topic, payload, qos=2)
        result.wait_for_publish(timeout=MESSAGE_TIMEOUT)

        assert done.wait(timeout=MESSAGE_TIMEOUT), "QoS 2 message not received"
        time.sleep(0.5)
        assert len(received) == 1, f"Expected exactly 1 delivery, got {len(received)}"
        assert received[0] == payload

        for c in (sub, pub):
            c.loop_stop()
            c.disconnect()

    def test_payload_integrity(self):
        """TC-PS-04: JSON payload is transmitted without corruption."""
        topic = f"{BASE_TOPIC}/payload-integrity"
        sensor_data = {
            "device_id": "sensor-001",
            "temperature": 23.7,
            "humidity": 61.2,
            "timestamp": 1712345678,
            "status": "ok",
        }
        received, done = [], threading.Event()
        sub = make_client("tc-ps-04-sub")

        def on_msg(client, ud, msg):
            received.append(json.loads(msg.payload.decode()))
            done.set()

        sub.on_message = on_msg
        sub.subscribe(topic, qos=1)
        time.sleep(0.2)

        pub = make_client("tc-ps-04-pub")
        pub.publish(topic, json.dumps(sensor_data), qos=1)

        assert done.wait(timeout=MESSAGE_TIMEOUT)
        assert received[0] == sensor_data, "Payload was corrupted in transit"

        for c in (sub, pub):
            c.loop_stop()
            c.disconnect()


# ── Tests: Retained Messages ──────────────────────────────────────────────────


class TestRetainedMessages:
    def test_retained_message_delivered_on_subscribe(self):
        """TC-RET-01: New subscriber receives the last retained message immediately."""
        topic, payload = f"{BASE_TOPIC}/retained", "retained-value-42"

        pub = make_client("tc-ret-01-pub")
        pub.publish(topic, payload, qos=1, retain=True)
        time.sleep(0.3)
        pub.loop_stop()
        pub.disconnect()

        messages = subscribe_and_collect(topic, qos=1, client_id="tc-ret-01-sub")
        assert len(messages) >= 1, "Retained message not delivered on subscribe"
        assert messages[0]["payload"] == payload
        assert messages[0]["retain"] is True

    def test_clear_retained_message(self):
        """TC-RET-02: Publishing empty payload clears a retained message."""
        topic = f"{BASE_TOPIC}/clear-retained"

        pub = make_client("tc-ret-02-pub")
        pub.publish(topic, "to-be-cleared", qos=1, retain=True)
        time.sleep(0.3)
        pub.publish(topic, "", qos=1, retain=True)
        time.sleep(0.3)
        pub.loop_stop()
        pub.disconnect()

        messages = subscribe_and_collect(
            topic, qos=1, client_id="tc-ret-02-sub", timeout=2
        )
        non_empty = [m for m in messages if m["payload"] != ""]
        assert len(non_empty) == 0, "Retained message was not cleared"


# ── Tests: Wildcards ──────────────────────────────────────────────────────────


class TestWildcards:
    def test_single_level_wildcard(self):
        """TC-WILD-01: '+' matches exactly one topic level."""
        wildcard = f"{BASE_TOPIC}/sensors/+/temperature"
        sensor_a = f"{BASE_TOPIC}/sensors/device-a/temperature"
        sensor_b = f"{BASE_TOPIC}/sensors/device-b/temperature"

        received, done = [], threading.Event()
        sub = make_client("tc-wild-01-sub")

        def on_msg(client, ud, msg):
            received.append(msg.topic)
            if len(received) >= 2:
                done.set()

        sub.on_message = on_msg
        sub.subscribe(wildcard, qos=0)
        time.sleep(0.2)

        pub = make_client("tc-wild-01-pub")
        pub.publish(sensor_a, "22.1", qos=0)
        pub.publish(sensor_b, "24.3", qos=0)

        assert done.wait(timeout=MESSAGE_TIMEOUT), (
            "Wildcard did not receive both messages"
        )
        assert sensor_a in received
        assert sensor_b in received

        for c in (sub, pub):
            c.loop_stop()
            c.disconnect()

    def test_multi_level_wildcard(self):
        """TC-WILD-02: '#' matches all descendant topic levels."""
        base = f"{BASE_TOPIC}/fleet"
        wildcard = f"{base}/#"
        topics = [
            f"{base}/truck-01/gps",
            f"{base}/truck-01/fuel",
            f"{base}/truck-02/gps",
        ]

        received, done = [], threading.Event()
        sub = make_client("tc-wild-02-sub")

        def on_msg(client, ud, msg):
            received.append(msg.topic)
            if len(received) >= len(topics):
                done.set()

        sub.on_message = on_msg
        sub.subscribe(wildcard, qos=0)
        time.sleep(0.2)

        pub = make_client("tc-wild-02-pub")
        for t in topics:
            pub.publish(t, "data", qos=0)

        assert done.wait(timeout=MESSAGE_TIMEOUT), (
            "Multi-level wildcard missed messages"
        )
        for t in topics:
            assert t in received

        for c in (sub, pub):
            c.loop_stop()
            c.disconnect()


# ── Tests: Last Will & Testament ──────────────────────────────────────────────


class TestLastWill:
    def test_last_will_delivered_on_ungraceful_disconnect(self):
        """TC-LWT-01: LWT message published when client disconnects ungracefully."""
        lwt_topic = f"{BASE_TOPIC}/lwt/device-offline"
        lwt_payload = json.dumps({"status": "offline", "device": "iot-device-001"})

        received, done = [], threading.Event()
        watcher = make_client("tc-lwt-01-watcher")

        def on_msg(client, ud, msg):
            received.append(json.loads(msg.payload.decode()))
            done.set()

        watcher.on_message = on_msg
        watcher.subscribe(lwt_topic, qos=1)
        time.sleep(0.2)

        device = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id="tc-lwt-01-device"
        )
        device.will_set(lwt_topic, lwt_payload, qos=1, retain=False)
        device.connect(BROKER_HOST, BROKER_PORT)
        device.loop_start()
        time.sleep(0.3)

        # Force ungraceful disconnect
        device.loop_stop()
        device._sock.close()

        assert done.wait(timeout=10), "LWT message was not published"
        assert received[0]["status"] == "offline"

        watcher.loop_stop()
        watcher.disconnect()


# ── Tests: Message Ordering ───────────────────────────────────────────────────


class TestMessageOrdering:
    def test_message_ordering_qos1(self):
        """TC-ORD-01: Messages arrive in published order at QoS 1."""
        topic, count = f"{BASE_TOPIC}/ordering", 20
        received, done = [], threading.Event()
        sub = make_client("tc-ord-01-sub")

        def on_msg(client, ud, msg):
            received.append(int(msg.payload.decode()))
            if len(received) >= count:
                done.set()

        sub.on_message = on_msg
        sub.subscribe(topic, qos=1)
        time.sleep(0.2)

        pub = make_client("tc-ord-01-pub")
        for i in range(count):
            pub.publish(topic, str(i), qos=1)

        assert done.wait(timeout=MESSAGE_TIMEOUT * 2), "Not all messages received"
        assert received == list(range(count)), f"Messages out of order: {received}"

        for c in (sub, pub):
            c.loop_stop()
            c.disconnect()

    def test_high_frequency_publish(self):
        """TC-ORD-02: Broker handles 100 rapid messages without loss at QoS 1."""
        topic, count = f"{BASE_TOPIC}/high-freq", 100
        received, done = [], threading.Event()
        sub = make_client("tc-ord-02-sub")

        def on_msg(client, ud, msg):
            received.append(msg.payload.decode())
            if len(received) >= count:
                done.set()

        sub.on_message = on_msg
        sub.subscribe(topic, qos=1)
        time.sleep(0.2)

        pub = make_client("tc-ord-02-pub")
        for i in range(count):
            pub.publish(topic, f"msg-{i}", qos=1)

        assert done.wait(timeout=15), f"Only received {len(received)}/{count} messages"
        assert len(received) == count

        for c in (sub, pub):
            c.loop_stop()
            c.disconnect()
