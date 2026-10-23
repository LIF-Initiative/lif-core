"""The key a child appears under in its parent's schema, stored as the association's Name (#1386).

The schema generator builds these keys, and V1.7 backfilled the same rules into
EntityAssociation.Name / EntityAttributeAssociation.Name and their Array columns. Create paths use
these functions so new rows match. No MDR imports here: the services that create associations are
imported by schema_generation_service, so the rules can't live there.
"""


def embedded_property_key(relationship, entity_name):
    """The property key an Embedded child is stored under in its parent's schema.

    Single source of truth for a rule that used to be written out by hand in
    ``find_children`` and assumed-away in ``add_ref``. The key is
    ``Relationship + EntityName``, except when the relationship is absent or is a
    structural ``has*`` / ``relevant*`` name, where it collapses to the bare entity
    name.

    ``add_ref`` navigates schemas that ``find_children`` built, so both must spell
    the key the same way. They did not, and a named Embedded ancestor made
    ``add_ref`` look up a key that was never written -- an uncaught ``KeyError``
    surfacing as a bare 500 (#1252).
    """
    if relationship is not None and not (relationship.startswith("has") or relationship.startswith("relevant")):
        return relationship + entity_name
    return entity_name


def reference_property_key(relationship, entity_name):
    """The property key ``add_ref`` stores a Reference child under: ``Ref`` + the entity name,
    prefixed by the relationship unless it is absent or a structural ``has*`` / ``relevant*`` name."""
    if relationship is None or relationship.startswith(("has", "relevant")):
        return "Ref" + entity_name
    return relationship + "Ref" + entity_name


def entity_association_name(relationship, placement, child_name):
    """EntityAssociation.Name: the Reference key for a Reference child, else the Embedded key.

    Case is kept as stored (spec §5.4: migrated names keep today's keys).
    """
    if placement == "Reference":
        return reference_property_key(relationship, child_name)
    return embedded_property_key(relationship, child_name)


def association_array(child_array):
    """Association Array: whether the child is a list under this parent (its ``Array`` is ``'Yes'``)."""
    return child_array == "Yes"


def recomputed(stored, before, after):
    """The value an update stores: the rule's new value while the stored one is still the rule's.

    ``before`` is what the rule gave for the row before the edit, ``after`` what it gives now. A stored
    value equal to ``before``, or NULL (not computed yet), came from the rule, so it follows the edit.
    Any other value was set some other way (a model import writes Name and Array from the file, and
    #1388 sets Names that resolve collisions), so the edit leaves it alone.
    """
    return after if stored is None or stored == before else stored
