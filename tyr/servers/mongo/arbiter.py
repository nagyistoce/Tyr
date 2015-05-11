from member import MongoReplicaSetMember

class MongoArbiterNode(MongoReplicaSetMember):

    NAME_TEMPLATE = '{envcl}-rs{replica_set}-{location}-arb'
    NAME_SEARCH_PREFIX = '{envcl}-rs{replica_set}-{location}-'
    NAME_AUTO_INDEX=False

    CHEF_RUNLIST = ['role[RoleMongo]']
    CHEF_MONGODB_TYPE = 'arbiter'

    def __init__(self, group = None, server_type = None, instance_type = None,
                    environment = None, ami = None, region = None, role = None,
                    keypair = None, availability_zone = None,
                    security_groups = None, block_devices = None,
                    chef_path = None, subnet_id = None, replica_set = None,
                    mongodb_version = None):

        super(MongoArbiterNode, self).__init__(group, server_type, instance_type,
                                                environment, ami, region, role,
                                                keypair, availability_zone,
                                                security_groups, block_devices,
                                                chef_path, subnet_id,
                                                replica_set,
                                                mongodb_version)

    def bake(self):

        super(MongoArbiterNode, self).bake()

        with self.chef_api:

            self.chef_node.attributes.set_dotted('hudl_ebs.volumes', [
                {
                    'user': 'mongod',
                    'group': 'mongod',
                    'size': 1,
                    'iops': 0,
                    'device': '/dev/xvdf',
                    'mount': '/volr'
                }
            ])

            self.log.info('Configured the hudl_ebs.volumes attribute')

            self.chef_node.attributes.set_dotted('mongodb.config.smallfiles', True)

            self.chef_node.save()
            self.log.info('Saved the Chef Node configuration')
