"""Launch file for the RRCF ROS 2 bridge node.

Usage:
    ros2 launch rrcf_ros2_bridge rrcf_bridge.launch.py \\
        rrcf_file:=/path/to/robot.rrcf \\
        cmd_vel_topic:=/cmd_vel \\
        estop_topic:=/rrcf/estop
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    rrcf_file_arg = DeclareLaunchArgument(
        "rrcf_file", description="Path to the robot's .rrcf file (required)"
    )
    cmd_vel_topic_arg = DeclareLaunchArgument("cmd_vel_topic", default_value="/cmd_vel")
    estop_topic_arg = DeclareLaunchArgument(
        "estop_topic", default_value="", description="Defaults to the .rrcf file's declared estop topic"
    )
    skill_topic_prefix_arg = DeclareLaunchArgument(
        "skill_topic_prefix", default_value="", description="Defaults to /rrcf/<slug>/skill"
    )
    mqtt_broker_arg = DeclareLaunchArgument(
        "mqtt_broker_override", default_value="", description="Overrides ${MQTT_BROKER} in the .rrcf file"
    )
    mqtt_port_arg = DeclareLaunchArgument("mqtt_port", default_value="1883")

    bridge_node = Node(
        package="rrcf_ros2_bridge",
        executable="bridge_node",
        name="rrcf_bridge_node",
        output="screen",
        parameters=[
            {
                "rrcf_file": LaunchConfiguration("rrcf_file"),
                "cmd_vel_topic": LaunchConfiguration("cmd_vel_topic"),
                "estop_topic": LaunchConfiguration("estop_topic"),
                "skill_topic_prefix": LaunchConfiguration("skill_topic_prefix"),
                "mqtt_broker_override": LaunchConfiguration("mqtt_broker_override"),
                "mqtt_port": LaunchConfiguration("mqtt_port"),
            }
        ],
    )

    return LaunchDescription(
        [
            rrcf_file_arg,
            cmd_vel_topic_arg,
            estop_topic_arg,
            skill_topic_prefix_arg,
            mqtt_broker_arg,
            mqtt_port_arg,
            bridge_node,
        ]
    )
