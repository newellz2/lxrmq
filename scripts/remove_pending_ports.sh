ETCD_CA=ssl/ca.pem
ETCD_CERT=ssl/lx-client.pem
ETCD_CERT_KEY=ssl/lx-client-key.pem
ETCD_ENDPOINTS=10.100.100.10:2379

etcdctl \
--cacert ${ETCD_CA} --cert ${ETCD_CERT} --key ${ETCD_CERT_KEY} \
--endpoints=${ETCD_ENDPOINTS} \
del /lxd/pending_ports
