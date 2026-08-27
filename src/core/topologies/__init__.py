"""
==== Policy ====
All topology data structure implementations must implement the Cell protocol from core.engine. It is also the topology
data structure's responsibility to track attributes. While Cell values can be changed elsewhere, the best practice for
maximum cohesion is to have the topology take care of attribute updates. This means that attributes important to
causality tracking are managed by the topology (such as a cell's ID, or it's gen/created_at attributes).
Additionally, topologies are responsible for using find/search algorithms designed for their data structures. All
underlying data structures must remain simple (i.e. not implement specialized substitution methods, for instance.)
"""
