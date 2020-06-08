import boto3
import botocore
import click
import datetime

###############################################
## SNAPSHOTS
##    list
## VOLUMES
##    list
## INSTANCES
##    list
##    snapshot
##    stop
##    start
##    reboot
###############################################

session = None
ec2 = None

###############################################
## General functions
##    filter_instances
##    has_pending_snapshot
##    last_successful_snapshot
###############################################

###############################################
##    filter_instances
###############################################
def filter_instances(project, instance=None):
    instances = []
    filters = []

    # If project and/or instance supplied then build up the filter
    # If both supplied this means the instance must belong to the
    # project to be listed
    if project:
        filters.append({'Name':'tag:project', 'Values':[project]})

    if instance:
        filters.append({'Name':'instance-id', 'Values':[instance]})

    if project or instance:
        instances = ec2.instances.filter(Filters=filters)
    else:
        instances = ec2.instances.all()

    return instances

###############################################
##    has_pending_snapshot
###############################################
def has_pending_snapshot(volume):
    snapshots = list(volume.snapshots.all())
    return snapshots and snapshots[0].state == 'pending'

###############################################
##    last_successful_snapshot
###############################################
def last_successful_snapshot(volume):
    snapshots = list(volume.snapshots.all())
    last_snap = None
    for s in snapshots:
        if s.state == 'completed':
            last_snap = s
            break;

    return last_snap

###############################################
## Click group
###############################################
@click.group()
@click.option('--profile', default="shotty",
    help="--profile=<Profile Name>")
@click.option('--region', default="us-east-1",
    help="--region=<Region Name>")
def cli(profile, region):
    """Shotty manages snapshots"""
    global session, ec2

    session_cfg={}
    if profile:
        session_cfg['profile_name'] = profile
        session_cfg['region_name'] = region

    session = boto3.Session(**session_cfg)
    ec2 = session.resource('ec2')

###############################################
## SNAPSHOTS
##    list
###############################################
@cli.group('snapshots')
def snapshots():
    """Commands for snapshots"""

###############################################
## SNAPSHOTS
##    list
###############################################
@snapshots.command('list')
@click.option('--project', default=None,
    help="Only snapshots for project (tag Project:<name>)")
@click.option('--instance', 'instance', default=None,
    help="Only specific instance id")
@click.option('--all', 'list_all', default=False, is_flag=True,
    help="List all snapshots for each volume, not just the most recent")
def list_snapshots(project, instance, list_all):
    "List EC2 snapshots"

    instances = filter_instances(project, instance)

    for i in instances:
        for v in i.volumes.all():
            for s in v.snapshots.all():
                print(", ".join((
                    s.id,
                    v.id,
                    i.id,
                    s.state,
                    s.progress,
                    s.start_time.strftime("%c")
                )))

                if s.state == 'completed' and not list_all: break

    return

###############################################
## VOLUMES
##    list
###############################################
@cli.group('volumes')
def volumes():
    """Commands for volumes"""

###############################################
## VOLUMES
##    list
###############################################
@volumes.command('list')
@click.option('--project', default=None,
    help="Only volumes for project (tag Project:<name>)")
@click.option('--instance', 'instance', default=None,
    help="Only specific instance id")
def list_volumes(project, instance):
    "List EC2 volumes"

    instances = filter_instances(project, instance)

    for i in instances:
        for v in i.volumes.all():
            print(", ".join((
                v.id,
                i.id,
                v.state,
                str(v.size) + "GiB",
                v.encrypted and "Encrypted" or "Not Encrypted"
            )))

    return

###############################################
## INSTANCES
##    list
##    stop
##    start
##    snapshot
##    reboot
##    terminate
###############################################
@cli.group('instances')
def instances():
    """Commands for instances"""

###############################################
## INSTANCES
##    list
###############################################
@instances.command('list')
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
def list_instances(project):
    "List EC2 instances"

    instances = filter_instances(project)

    for i in instances:
        tags = { t['Key']: t['Value'] for t in i.tags or [] }
        print(', '.join((
            i.id,
            i.instance_type,
            i.placement['AvailabilityZone'],
            i.state['Name'],
            i.public_dns_name,
            tags.get('project', '<no project>')
            )))

    return

###############################################
## INSTANCES
##    snapshot
###############################################
@instances.command('snapshot',
    help="Create snapshot of all volumes")
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
@click.option('--instance', 'instance', default=None,
    help="Only specific instance id")
@click.option('--force', 'force', default=False, is_flag=True,
    help="If the project is not specified then  proceed if the force flag is set")
@click.option('--age', 'age', default=0,
    help="Only snapshot the volume if it's not happened in the last <age> days")
def create_snapshots(project, instance, force, age):
    "Create snapshot for EC2 instances"

    if not (project or instance) and not force:
        print('No project or instance specified and force flag not set')
        return

    instances = filter_instances(project, instance)

    for i in instances:

        requires_restart = False
        do_snapshot = True

        for v in i.volumes.all():
            if age > 0:
                last_snap = last_successful_snapshot(v)
                last_snap_time = last_snap.start_time.replace(tzinfo=None)
                now = datetime.datetime.now().replace(tzinfo=None)
                if now <= last_snap_time + datetime.timedelta(days=age):
                    do_snapshot = False
                else:
                    do_snapshot = True

            if has_pending_snapshot(v):
                print("   Skipping {0}, snapshot already in progress".format(v.id))
                continue
            elif do_snapshot:

                if i.state['Name'] == 'running':
                    print("Stopping {0}...".format(i.id))

                    i.stop()
                    i.wait_until_stopped()
                    requires_restart = True

                print("   Creating snapshot of {0}".format(v.id))
                v.create_snapshot(Description="Created by SnapshotAlyzer 30000")
            else:
                print("   Skipping, {0} created in last {1} day(s)".format(last_snap.id, str(age)))

        if requires_restart:
            print("Starting {0}".format(i.id))

            i.start()
            i.wait_until_running()

    print("Job's done!")

    return

###############################################
## INSTANCES
##    stop
###############################################
@instances.command('stop')
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
@click.option('--instance', 'instance', default=None,
    help="Only specific instance id")
@click.option('--force', 'force', default=False, is_flag=True,
    help="If the project is not specified then only proceed if the force flag is set")
def stop_instances(project, instance, force):
    "Stop EC2 instances"

    if not (project or instance) and not force:
        print('No project or instance specified and force flag not set')
        return

    instances = filter_instances(project, instance)

    for i in instances:
        print("Stopping {0}...".format(i.id))
        try:
            i.stop()
        except botocore.exceptions.ClientError as e:
            print("   Could not stop {0}. ".format(i.id) + str(e))
            continue

    return

###############################################
## INSTANCES
##    start
###############################################
@instances.command('start')
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
@click.option('--instance', 'instance', default=None,
    help="Only specific instance id")
@click.option('--force', 'force', default=False, is_flag=True,
    help="If the project is not specified then only proceed if the force flag is set")
def start_instances(project, instance, force):
    "Start EC2 instances"

    if not (project or instance) and not force:
        print('No project or instance specified and force flag not set')
        return

    instances = filter_instances(project, instance)

    for i in instances:
        print("Starting {0}...".format(i.id))
        try:
            i.start()
        except botocare.exceptions.ClientError as e:
            print("   Could not start {0}. ".format(i.id) + str(e))
            continue

    return

###############################################
## INSTANCES
##    reboot
###############################################
@instances.command('reboot')
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
@click.option('--instance', 'instance', default=None,
    help="Only specific instance id")
@click.option('--force', 'force', default=False, is_flag=True,
    help="If the project is not specified then only proceed if the force flag is set")
def reboot_instances(project, instance, force):
    "Reboot EC2 instances"

    if not (project or instance) and not force:
        print('No project or instance specified and force flag not set')
        return

    instances = filter_instances(project, instance)

    for i in instances:
        print("Rebooting {0}...".format(i.id))
        try:
            i.reboot()
        except botocare.exceptions.ClientError as e:
            print("   Could not reboot {0}. ".format(i.id) + str(e))
            continue

    return

###############################################
## INSTANCES
##    terminate
###############################################
@instances.command('terminate')
@click.option('--project', default=None,
    help="Only instances for project (tag Project:<name>)")
@click.option('--instance', 'instance', default=None,
    help="Only specific instance id")
@click.option('--force', 'force', default=False, is_flag=True,
    help="If the project is not specified then only proceed if the force flag is set")
def terminate_instances(project, instance, force):
    "Terminate EC2 instances"

    if not (project or instance) and not force:
        print('No project or instance specified and force flag not set')
        return

    instances = filter_instances(project, instance)

    for i in instances:
        print("Terminating {0}...".format(i.id))
        try:
            i.terminate()
        except botocare.exceptions.ClientError as e:
            print("   Could not terminate {0}. ".format(i.id) + str(e))
            continue

    return

###############################################
## MAIN
###############################################
if __name__ == '__main__':
    cli()
