from setuptools import setup

setup(
    name='snapshotalyzer-30000',
    version='0.2',
    author="Craig Dalrymple",
    author_email="craig.dalrymple91@gmail.com",
    description="SnapshotAlyzer 30000 is a tool to manage EC2 snapshots. Created during Robin Norwood's Python course on acloudguru",
    license="GPLv3+",
    packages=['shotty'],
    url="https://github.com/craig-python/snapshotalyzer-30000",
    install_requires=[
        'click',
        'boto3'
    ],
    entry_points='''
        [console_scripts]
        shotty=shotty.shotty:cli
    ''',
)
