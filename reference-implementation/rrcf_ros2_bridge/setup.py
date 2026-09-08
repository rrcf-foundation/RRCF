from setuptools import find_packages, setup

package_name = "rrcf_ros2_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/rrcf_bridge.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="RRCF Foundation",
    maintainer_email="hello@rrcf.io",
    description=(
        "Reference ROS 2 bridge that makes an existing robot RRCF-transport "
        "compliant without rewriting its control stack."
    ),
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "bridge_node = rrcf_ros2_bridge.bridge_node:main",
        ],
    },
)
