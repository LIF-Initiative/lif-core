import json
import re
from typing import List
from lif.datatypes.mdr_sql_model import (
    Attribute,
    DataModel,
    Entity,
    EntityAssociation,
    EntityAttributeAssociation,
    EntityPlacementType,
    Transformation,
    TransformationAttribute,
    TransformationGroup,
)
from lif.mdr_services.jinja_helper_service import jinja_creation
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
import pandas as pd
from sqlalchemy import or_, and_

from lif.mdr_utils.logger_config import get_logger


logger = get_logger(__name__)


async def get_all_entity_data_frame(session: AsyncSession, data_model_ids: List[int] = None):
    entity_query = select(Entity.Id, Entity.Name).where(
        Entity.Deleted == False, (Entity.DataModelId.in_(data_model_ids) if data_model_ids else True)
    )
    execution = await session.execute(entity_query)
    result = execution.fetchall()
    column_names = result[0]._fields if result else []
    df_entity = pd.DataFrame(result, columns=column_names)
    return df_entity


async def get_complete_entity_tree(rows, df_entity, distinctEntityIds: List[int] = None):
    tree = {}
    top_level_parents = []
    parent_id_list = []
    child_id_list = []
    for row in rows:
        parent = row[0]
        child = row[1]
        if parent not in parent_id_list:
            parent_id_list.append(parent)
        if distinctEntityIds and child in distinctEntityIds:
            if child not in child_id_list:
                child_id_list.append(child)
            if parent in tree:
                tree[parent].append(child)
            else:
                tree[parent] = [child]
        if not distinctEntityIds:
            if child not in child_id_list:
                child_id_list.append(child)
            if parent in tree:
                tree[parent].append(child)
            else:
                tree[parent] = [child]

    top_level_parents = [p for p in parent_id_list if p not in child_id_list]

    logger.info(f"tree : {tree}")
    logger.info(f"parent_id_list : {parent_id_list}")
    logger.info(f"child_id_list : {child_id_list}")
    logger.info(f"top_level_parents : {top_level_parents}")

    tree_with_entity_names = {}
    for parent, child_list in tree.items():
        parent_entity_name = (df_entity[df_entity["Id"] == parent])["Name"].unique().tolist()[0]
        # logger.info(f"parent_entity_name : {parent_entity_name}")
        if isinstance(child_list, list) and len(child_list) > 0:
            tree_with_entity_names[parent_entity_name] = []
            for child_entity_id in child_list:
                child_entity_name = (df_entity[df_entity["Id"] == child_entity_id])["Name"].unique().tolist()[0]
                # logger.info(f"child_entity_name : {child_entity_name}")
                tree_with_entity_names[parent_entity_name].append(child_entity_name)
    logger.info(f"tree_with_entity_names : {tree_with_entity_names}")

    top_level_entity_names = []
    for entity_id in top_level_parents:
        parent_entity_name = (df_entity[df_entity["Id"] == entity_id])["Name"].unique().tolist()[0]
        top_level_entity_names.append(parent_entity_name)
    logger.info(f"top_level_entity_names : {top_level_entity_names}")

    return tree, parent_id_list, child_id_list, top_level_parents, tree_with_entity_names, top_level_entity_names


async def extend_subtree(main_tree, initial_subtree, entities):
    # Create a reverse mapping from child to parent
    parent_map = {}
    for parent, children in main_tree.items():
        for child in children:
            parent_map[child] = parent

    # Function to add parent and filtered children to the subtree
    def add_to_subtree(subtree, node):
        if node in parent_map:
            parent = parent_map[node]
            if parent not in subtree:
                # Filter children to only include those in the entities list
                filtered_children = [child for child in main_tree[parent] if child in entities]
                subtree[parent] = filtered_children

    # Extend the subtree
    for entity in entities:
        add_to_subtree(initial_subtree, entity)

    return initial_subtree


async def get_data_model_id_by_name_and_version(session: AsyncSession, name: str, version: str) -> int:
    query = select(DataModel.Id).where(
        DataModel.Name == name, DataModel.DataModelVersion == version, DataModel.Deleted == False
    )
    result = await session.execute(query)
    data_model_id = result.scalar()

    return data_model_id


async def find_ancestors(tree, child, inter_entity_placement=None):
    logger.info(" ########## in find_ancestors ########## ")
    # Create a reverse mapping from child to parent
    parent_map = {}
    for parent, children in tree.items():
        # logger.info(f"parent: {parent}")
        # logger.info(f"children: {children}")
        for c in children:
            if inter_entity_placement:
                if c in inter_entity_placement:
                    if (
                        inter_entity_placement[c]["ParentEntityId"] == parent
                        and inter_entity_placement[c]["Placement"] == EntityPlacementType.Reference
                    ):
                        # If the child is a reference in parent then do not put that child in parent map.
                        logger.info(f"Child {c} is a {inter_entity_placement[c]['Placement']} for parent {parent}")
                        continue
            parent_map[c] = parent

    logger.info(f"parent_map: {parent_map}")
    # List to store the ancestors
    ancestors = []

    # Trace back from the child to the root, collecting ancestors
    while child in parent_map:
        parent = parent_map[child]
        ancestors.append(parent)
        child = parent
    # logger.info(f"Ancestors before reverse {ancestors}")

    # Reversing list to get the main root entity as the first element and so on..
    ancestors.reverse()

    # logger.info(f"Ancestors after reverse {ancestors}")

    return ancestors


# async def create_entity_v2(entity_id, children=None):
#     entity = {
#         "id": entity_id,
#         "type": "Entity",
#         "obj_type": "array",
#         "data_model": "LIF",
#         "attributes": []
#     }
#     if children:
#         entity["children"] = children
#     return entity

# # Recursive function to build the tree structure
# async def build_tree(tree, root):
#     if root not in tree:
#         return await create_entity_v2(root)

#     children = [await build_tree(tree, child) for child in tree[root]]
#     return await create_entity_v2(root, children)


async def create_entity_v2(entity_id, children=None, parent=None, inter_entity_placement=None):
    logger.info("In create_entity_v2 ")
    logger.info(f"entity_id : {entity_id}")
    logger.info(f"children : {children}")
    logger.info(f"inter_entity_placement : {inter_entity_placement}")

    entity = {
        "id": entity_id,
        "type": "Entity",
        "target_entity_obj_type": "array",
        "data_model": "LIF",
        "attributes": [],
        "children": [],
    }
    if children:
        entity["children"] = children

    if inter_entity_placement and entity_id in inter_entity_placement:
        if inter_entity_placement[entity_id]["ParentEntityId"] == parent:
            logger.info("Entity is in placement list..")
            entity["Relationship"] = inter_entity_placement[entity_id]["Relationship"]
            entity["Placement"] = inter_entity_placement[entity_id]["Placement"]

    return entity


# Recursive function to build the tree structure
async def build_tree(tree, root, parent=None, inter_entity_placement=None):
    logger.info(" In build_tree ------")
    logger.info(f"tree : {tree}")
    logger.info(f"root : {root}")
    logger.info(f"inter_entity_placement : {inter_entity_placement}")
    if root not in tree:
        return await create_entity_v2(root, parent=parent, inter_entity_placement=inter_entity_placement)

    # children =[]
    # for child in tree[root]:
    #     if inter_entity_placement and root in inter_entity_placement:
    #         if child == inter_entity_placement[root]["ChildEntityId"]:
    #             children.append(build_tree(tree, child, inter_entity_placement[root]))
    #     else:
    #         children.append(build_tree(tree, child))

    children = [await build_tree(tree, child, root, inter_entity_placement) for child in tree[root]]
    return await create_entity_v2(root, children, parent=parent, inter_entity_placement=inter_entity_placement)


# Function to find all parents and their paths
async def find_paths_to_root(tree, entity, path=None, inter_entity_placement=None):
    if path is None:
        path = [entity]  # Start path with the entity

    all_paths = []
    logger.info(f"-- entity : {entity}")
    # Traverse the tree to find parents of the given entity
    for parent, children in tree.items():
        # logger.info(f"-- parent : {parent}")
        # logger.info(f"-- children : {children}")
        if entity in children:
            # logger.info(f"-- entity is in children")
            if (
                inter_entity_placement
                and entity in inter_entity_placement
                and inter_entity_placement[entity]["ParentEntityId"] == parent
                and inter_entity_placement[entity]["Placement"] == EntityPlacementType.Reference
            ):
                logger.info(
                    f" -- Child {entity} is a {inter_entity_placement[entity]['Placement']} for parent {parent} --"
                )
                continue
            # If parent is found, add the parent to the path
            new_path = [parent] + path
            # logger.info(f"-- new_path : {new_path}")
            # Recursively find further ancestors
            all_paths.extend(await find_paths_to_root(tree, parent, new_path, inter_entity_placement))

    # If no more parents are found, return the current path (reached root)
    if not all_paths:
        all_paths.append(path)

    logger.info(f"-- all_paths : {all_paths}")
    return all_paths


# Function to create a dictionary of paths for all entities
async def create_paths_dict(tree, inter_entity_placement, df_entity):
    all_paths_dict = {}

    # Iterate over all entities in the tree
    entities = {child for children in tree.values() for child in children}

    for entity in entities:
        # Get all paths to the root for each entity
        paths = await find_paths_to_root(tree=tree, entity=entity, inter_entity_placement=inter_entity_placement)

        # Remove the entity itself from the path (keep only the parent path)
        # filtered_paths = [path[:-1] for path in paths]

        # Store the result in the dictionary
        all_paths_dict[entity] = paths

    all_paths_dict_with_entity_names = {}
    for parent, child_list in all_paths_dict.items():
        # parent_entity_name = (df_entity[df_entity['Id'] == parent])["Name"].unique().tolist()[0]
        # logger.info(f"parent_entity_name : {parent_entity_name}")
        if isinstance(child_list, list) and len(child_list) > 0:
            all_paths_dict_with_entity_names[parent] = []
            for values in child_list:
                child_name_list = []
                for child_entity_id in values:
                    child_entity_name = (df_entity[df_entity["Id"] == child_entity_id])["Name"].unique().tolist()[0]
                    child_name_list.append(child_entity_name)
                # logger.info(f"child_entity_name : {child_entity_name}")
                all_paths_dict_with_entity_names[parent].append(child_name_list)

    return all_paths_dict, all_paths_dict_with_entity_names


async def create_get_mapping_v2(
    mapping_json,
    target_entity_id,
    target_expression,
    target_attribute_name,
    source_attribute_name,
    source_entity_name,
    tree_for_target_df,
    target_attribute_data_type,
    is_target_attribute_array,
    is_target_entity_array,
    source_attribute_data_type,
    is_source_attribute_array,
    is_source_entity_array,
    inter_entity_placement,
):
    logger.info(" ... In create_get_mapping_v2 ...")
    logger.info(f"target_entity_id : {target_entity_id}")
    # logger.info(f"mapping_json : {mapping_json}")
    logger.info(f"target_attribute_name : {source_attribute_name}")
    # logger.info(f"source_entity_name : {source_entity_name}")

    logger.info(f"source_attribute_name : {source_attribute_name}")
    logger.info(f"source_entity_name : {source_entity_name}")
    ancestors = await find_ancestors(
        tree_for_target_df, target_entity_id, inter_entity_placement=inter_entity_placement
    )
    logger.info(f"ancestors : {ancestors}")
    if len(ancestors) > 0:
        # For child entities
        ancestors.append(target_entity_id)  # appending target_entity_id to get the final JSON
        logger.info(f" updated ancestors : {ancestors}")
        target_json = mapping_json[ancestors[0]]
        target_found = False
        if len(ancestors) > 1:
            for ancestor in ancestors:
                logger.info(f"ancestor : {ancestor}")
                for child in target_json["children"]:
                    if child["id"] == ancestor:
                        target_json = child
                        target_found = True
                        break
    else:
        # For root level entity
        target_json = mapping_json[target_entity_id]

    logger.info(f"target_json : {target_json}")

    source_mapping_data = {}
    source_mapping_data[target_attribute_name] = {}

    # Assuming : default attribute object type is array for target
    if not is_target_attribute_array or is_target_attribute_array == "Yes":
        source_mapping_data[target_attribute_name]["target_attribute_obj_type"] = "array"
    else:
        source_mapping_data[target_attribute_name]["target_attribute_obj_type"] = "Obj"

    # Assuming : default attribute data type as string for target
    if target_attribute_data_type:
        source_mapping_data[target_attribute_name]["target_attribute_data_type"] = target_attribute_data_type
    else:
        source_mapping_data[target_attribute_name]["target_attribute_data_type"] = "xsd:string"

    # Assuming : default attribute object type is array for source
    if not is_source_attribute_array or is_source_attribute_array == "Yes":
        source_mapping_data[target_attribute_name]["source_attribute_obj_type"] = "array"
    else:
        source_mapping_data[target_attribute_name]["source_attribute_obj_type"] = "Obj"

    # Assuming : default attribute data type as string for source
    if source_attribute_data_type:
        source_mapping_data[target_attribute_name]["source_attribute_data_type"] = source_attribute_data_type
    else:
        source_mapping_data[target_attribute_name]["source_attribute_data_type"] = "xsd:string"

    # Assuming : default entity object type is array for source
    if not is_source_entity_array or is_source_entity_array == "Yes":
        source_mapping_data[target_attribute_name]["source_entity_obj_type"] = "array"
    else:
        source_mapping_data[target_attribute_name]["source_entity_obj_type"] = "Obj"

    source_mapping_data[target_attribute_name]["source_entity"] = source_entity_name
    source_mapping_data[target_attribute_name]["source_attribute"] = source_attribute_name
    source_mapping_data[target_attribute_name]["expression"] = target_expression

    target_json["attributes"].append(source_mapping_data)

    # Assuming : default entity object type is array
    if not is_target_entity_array or is_target_entity_array == "Yes":
        target_json["target_entity_obj_type"] = "array"
    else:
        target_json["target_entity_obj_type"] = "Object"


async def create_attribute_mapping_dict(
    is_target_attribute_array,
    target_attribute_data_type,
    is_source_attribute_array,
    source_attribute_data_type,
    is_source_entity_array,
    source_entity_name,
    source_attribute_name,
    target_expression,
):
    source_mapping_data = {}
    # source_mapping_data[target_attribute_name] = {}

    # Assuming : default attribute object type is array for target
    if not is_target_attribute_array or is_target_attribute_array == "Yes":
        source_mapping_data["target_attribute_obj_type"] = "array"
    else:
        source_mapping_data["target_attribute_obj_type"] = "object"

    # Assuming : default attribute data type as string for target
    if target_attribute_data_type:
        source_mapping_data["target_attribute_data_type"] = target_attribute_data_type
    else:
        source_mapping_data["target_attribute_data_type"] = "xsd:string"

    # Assuming : default attribute object type is array for source
    if not is_source_attribute_array or is_source_attribute_array == "Yes":
        source_mapping_data["source_attribute_obj_type"] = "array"
    else:
        source_mapping_data["source_attribute_obj_type"] = "object"

    # Assuming : default attribute data type as string for source
    if source_attribute_data_type:
        source_mapping_data["source_attribute_data_type"] = source_attribute_data_type
    else:
        source_mapping_data["source_attribute_data_type"] = "xsd:string"

    # Assuming : default entity object type is array for source
    if not is_source_entity_array or is_source_entity_array == "Yes":
        source_mapping_data["source_entity_obj_type"] = "array"
    else:
        source_mapping_data["source_entity_obj_type"] = "object"

    source_mapping_data["source_entity"] = source_entity_name
    source_mapping_data["source_attribute"] = source_attribute_name
    source_mapping_data["expression"] = target_expression

    logger.info(f"source_mapping_data : {source_mapping_data}")

    return source_mapping_data


async def create_get_mapping_v3(
    mapping_json,
    target_entity_id,
    target_expression,
    target_attribute_name,
    source_attribute_name,
    source_entity_name,
    tree_for_target_df,
    target_attribute_data_type,
    is_target_attribute_array,
    is_target_entity_array,
    source_attribute_data_type,
    is_source_attribute_array,
    is_source_entity_array,
    inter_entity_placement,
    top_level_parents_for_target_df,
    paths_for_all_children,
    paths_for_all_children_with_name,
):
    logger.info(" ... In create_get_mapping_v3 ...")
    logger.info(f"target_entity_id : {target_entity_id}")
    # logger.info(f"mapping_json : {mapping_json}")
    logger.info(f"target_attribute_name : {target_attribute_name}")
    # logger.info(f"source_entity_name : {source_entity_name}")

    logger.info(f"source_attribute_name : {source_attribute_name}")
    logger.info(f"source_entity_name : {source_entity_name}")
    logger.info(f"top_level_parents_for_target_df : {top_level_parents_for_target_df}")
    # ancestors = await find_ancestors(tree_for_target_df,target_entity_id, inter_entity_placement=inter_entity_placement)
    # logger.info(f"ancestors : {ancestors}")

    all_paths_to_entity = paths_for_all_children[target_entity_id]
    logger.info(f"all_paths_to_entity : {all_paths_to_entity}")

    all_paths_to_entity_with_name = paths_for_all_children_with_name[target_entity_id]
    logger.info(f"all_paths_to_entity_with_name : {all_paths_to_entity_with_name}")

    if target_entity_id in top_level_parents_for_target_df:
        logger.info("This is top level entity")
        # For root level entity
        target_json = mapping_json[target_entity_id]
        # Assuming : default entity object type is array
        if not is_target_entity_array or is_target_entity_array == "Yes":
            target_json["target_entity_obj_type"] = "array"
        else:
            target_json["target_entity_obj_type"] = "Object"
    else:
        if "=" in target_expression:
            target_part = target_expression.split("=")[0]

        if "get(" in target_expression:
            target_part = target_expression.split("(")[1].split(",")[0]

        if "addAll(" in target_expression:
            target_part = target_expression.split("addAll")[0]
        logger.info(f"target_part : {target_part}")
        logger.info(f"target_expression : {target_expression}")
        list_of_ancestors = []
        for index, name_list in enumerate(all_paths_to_entity_with_name):
            logger.info(f"name_list : {name_list}")
            path = ".".join(name_list)
            logger.info(f"path : {path}")
            if path in target_part:
                list_of_ancestors.append(all_paths_to_entity[index])
        logger.info(f"list_of_ancestors : {list_of_ancestors}")
        for ancestors in list_of_ancestors:
            target_json = mapping_json[ancestors[0]]
            target_found = False
            if len(ancestors) > 1:
                for ancestor in ancestors:
                    logger.info(f"ancestor : {ancestor}")
                    for child in target_json["children"]:
                        if child["id"] == ancestor:
                            target_json = child
                            target_found = True
                            break

            logger.info(f"target_json : {target_json}")

            target_attribute_json = None
            target_attribute_found = False
            for attribute in target_json["attributes"]:
                for key, value_dict in attribute.items():
                    if target_attribute_name == key:
                        target_attribute_json = value_dict
                        target_attribute_found = True

            if not target_attribute_found:
                attribute_json = {}
                attribute_json[target_attribute_name] = []
                target_json["attributes"].append(attribute_json)
                target_attribute_json = attribute_json[target_attribute_name]

            source_mapping_data = await create_attribute_mapping_dict(
                is_target_attribute_array,
                target_attribute_data_type,
                is_source_attribute_array,
                source_attribute_data_type,
                is_source_entity_array,
                source_entity_name,
                source_attribute_name,
                target_expression,
            )

            target_attribute_json.append(source_mapping_data)
            # target_json['attributes'].append(target_attribute_json)

            # Assuming : default entity object type is array
            if not is_target_entity_array or is_target_entity_array == "Yes":
                target_json["target_entity_obj_type"] = "array"
            else:
                target_json["target_entity_obj_type"] = "Object"

    # parse expression get the entity ids where this attribute belongs
    # check all the paths and based on entities in expression put this attribute.


async def create_children_jinja_v2(child_json, sources_dict, jinja_dict, df_entity, first_level=False):
    logger.info(" ..... In create_children_jinja_v2 .... ")
    logger.info(f"child_json : {child_json}")
    logger.info(f"sources_dict : {sources_dict}")
    logger.info(f"jinja_dict : {jinja_dict}")
    # logger.info(f"parent_table_details : {parent_table_details}")
    # logger.info(f"tree_for_target_df : {tree_for_target_df}")
    # logger.info(f"jinja_dict : {jinja_dict}")

    # if parent_entity_name in tree_with_entity_names:
    #     for child_entity_name in tree_with_entity_names[parent_entity_name]:
    data_type = child_json["target_entity_obj_type"]
    child_entity_name = (df_entity[df_entity["Id"] == child_json["id"]])["Name"].unique().tolist()[0]
    logger.info(f"child_entity_name : {child_entity_name}")
    if "Relationship" in child_json:
        child_entity_name = child_json["Relationship"] + child_entity_name
        logger.info(f"after relationship child_entity_name : {child_entity_name}")

    if isinstance(jinja_dict, list):
        dict_data = jinja_dict[0]
    else:
        dict_data = jinja_dict
    if not first_level:
        if data_type == "array":
            dict_data[child_entity_name] = []
            obj = {}
        else:
            dict_data[child_entity_name] = {}

    logger.info(f"dict_data : {dict_data}")
    # if "Placement" in child_json and child_json['Placement'] == 'Reference':
    #     logger.info("This is reference..")
    #     return sources_dict

    for attribute in child_json["attributes"]:
        logger.info(f"attribute : {attribute}")
        for target_attribute_name, attribute_mapping_list in attribute.items():
            for attribute_mapping in attribute_mapping_list:
                logger.info(f"target_attribute_name : {target_attribute_name}")
                logger.info(f"attribute_mapping : {attribute_mapping}")
                source_entity = attribute_mapping["source_entity"]
                source_attribute = attribute_mapping["source_attribute"]
                source_value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
                if source_entity not in sources_dict:
                    sources_dict[source_entity] = f"    {{% set {source_entity} = fromjson({source_entity}) %}}\n"
                if first_level:
                    dict_data[target_attribute_name] = f"{{{{{source_value}}}}}"
                else:
                    if data_type == "array":
                        obj[target_attribute_name] = f"{{{{{source_value}}}}}"
                    else:
                        dict_data[child_entity_name][target_attribute_name] = f"{{{{{source_value}}}}}"
    if data_type == "array" and not first_level:
        dict_data[child_entity_name].append(obj)

    if "Placement" in child_json and child_json["Placement"] == "Reference":
        logger.info("This is reference..")
        return sources_dict

    if "children" in child_json:
        logger.info("Children")
        for child in child_json["children"]:
            if not first_level:
                await create_children_jinja_v2(
                    child_json=child,
                    sources_dict=sources_dict,
                    jinja_dict=dict_data[child_entity_name],
                    df_entity=df_entity,
                    first_level=False,
                )
            else:
                await create_children_jinja_v2(
                    child_json=child,
                    sources_dict=sources_dict,
                    jinja_dict=jinja_dict,
                    df_entity=df_entity,
                    first_level=False,
                )

    logger.info(f"jinja_dict (final) : {jinja_dict}")
    return sources_dict


async def jinja_creation_v6(top_level_json, visited_dict_add_columns, visited_dict_keep_column, df_entity):
    logger.info("  ********* In jinja_creation_v6 ************")
    logger.info(f"top_level_json : {top_level_json}")
    logger.info(f"visited_dict_add_columns : {visited_dict_add_columns}")
    logger.info(f"visited_dict_keep_column : {visited_dict_keep_column}")

    parent_data_type = top_level_json["target_entity_obj_type"]

    # Adding all direct attributes as a columns in jinja for child entity (1st layer after the root)
    for attribute in top_level_json["attributes"]:
        # logger.info(f"source : {source}")
        for target_attribute_name, attribute_mapping_list in attribute.items():
            # logger.info(f"source_entity : {source_entity}")
            # logger.info(f"attribute_mapping : {attribute_mapping}")
            for attribute_mapping in attribute_mapping_list:
                source_entity = attribute_mapping["source_entity"]
                source_attribute = attribute_mapping["source_attribute"]
                source_value = source_entity + "." + re.sub(r"[.\n: ]", "", source_attribute)
                sub_jinja = "  {% raw %}\n"
                # TODO : need to add code to check attribute type and create jinja based on that. Right now ww are assuming this as an array.
                sub_jinja += "  [ {\n"
                sub_jinja += f"    {{% set {source_entity} = fromjson({source_entity}) %}}\n"
                sub_jinja += f'      "{target_attribute_name}": "{{{{{source_value}}}}}"\n'
                sub_jinja += "  } ]\n"
                sub_jinja += "  {% endraw %}"
                visited_dict_add_columns[target_attribute_name] = sub_jinja
                visited_dict_keep_column.append(target_attribute_name)

    # adding all children (immediate children to root) as a column in jinja
    if "children" in top_level_json:
        for child in top_level_json["children"]:
            sources_dict = {}
            jinja_dict = {}
            child_entity_name = (df_entity[df_entity["Id"] == child["id"]])["Name"].unique().tolist()[0]
            logger.info(f"child_entity_name : {child_entity_name}")
            if "Relationship" in child:
                child_entity_name = child["Relationship"] + child_entity_name
                logger.info(f" ~~~ after relationship child_entity_name : {child_entity_name}")
            data_type = child["target_entity_obj_type"]
            template_str_part_1 = "  {% raw %}\n"
            if data_type == "array":
                template_str_part_1 += "  [ {\n"
            else:
                template_str_part_1 += "  {\n"

            await create_children_jinja_v2(
                child_json=child,
                sources_dict=sources_dict,
                jinja_dict=jinja_dict,
                df_entity=df_entity,
                first_level=True,
            )

            for source, jinja_str in sources_dict.items():
                template_str_part_1 += jinja_str

            if data_type == "array":
                template_str_part_2 = "  } ]\n"
            else:
                template_str_part_2 = "  }\n"
            template_str_part_2 += "  {% endraw %}"

            final_jinja_str = template_str_part_1 + json.dumps(jinja_dict, indent=4).strip("{}") + template_str_part_2

            logger.info(f"final_jinja_str : {final_jinja_str}")
            visited_dict_add_columns[child_entity_name] = final_jinja_str
            visited_dict_keep_column.append(child_entity_name)


async def get_base_model_ids(session: AsyncSession, data_model_id: int):
    # Initialize the list with the given extension model id
    base_model_ids = [data_model_id]

    # Start with the given extension model ID
    current_model_id = data_model_id

    # `is not None`, not truthiness: a DataModel id of 0 is a real id, and treating it as
    # "no more base models" would silently drop that model's ancestors from the walk.
    while current_model_id is not None:
        # Query to get the BaseDataModelId for the current model
        query = select(DataModel.BaseDataModelId).where(DataModel.Id == current_model_id)
        result = await session.execute(query)
        base_data_model_id = result.scalar()

        # If there is a base model, add it to the list and continue
        if base_data_model_id is not None:
            base_model_ids.append(base_data_model_id)
            current_model_id = base_data_model_id  # Set the current model ID to the base model ID
        else:
            break  # No more base models

    return base_model_ids


async def update_schema_for_lif_1(
    session: AsyncSession, tree_for_target_df, child_id_list_for_target_df, parent_id_list_for_target_df, lif_v1_Id
):
    # This means our target is LIF 1.0
    # Getting Person entity id
    query = select(Entity.Id).where(Entity.Name == "Person", Entity.DataModelId == lif_v1_Id, Entity.Deleted == False)
    result = await session.execute(query)
    person_lif_v1_Id = result.scalar()
    logger.info(f"person_lif_v1_Id: {person_lif_v1_Id}")

    # Getting CompetencyFramework entity id
    query = select(Entity.Id).where(
        Entity.Name == "CompetencyFramework", Entity.DataModelId == lif_v1_Id, Entity.Deleted == False
    )
    result = await session.execute(query)
    competency_framework_lif_v1_Id = result.scalar()
    logger.info(f"person_lif_v1_Id: {person_lif_v1_Id}")
    logger.info(f"competency_framework_lif_v1_Id : {competency_framework_lif_v1_Id}")

    if person_lif_v1_Id in tree_for_target_df.keys():
        for parent, child_list in tree_for_target_df.items():
            if (
                parent != person_lif_v1_Id
                and parent != competency_framework_lif_v1_Id
                and parent not in child_id_list_for_target_df
            ):
                tree_for_target_df[person_lif_v1_Id].append(parent)
    else:
        tree_for_target_df[person_lif_v1_Id] = []
        for parent, child_list in tree_for_target_df.items():
            if parent != competency_framework_lif_v1_Id and parent not in child_id_list_for_target_df:
                tree_for_target_df[person_lif_v1_Id].append(parent)
    logger.info(f"\n  +++++++++++++++++++++ tree_for_target_df : {tree_for_target_df} --- \n")
    for parent, child_list in tree_for_target_df.items():
        if parent not in parent_id_list_for_target_df:
            parent_id_list_for_target_df.append(parent)
        for child in child_list:
            if child not in child_id_list_for_target_df:
                child_id_list_for_target_df.append(child)
    logger.info(f"\n --- UPDATED parent_id_list_for_target_df : {parent_id_list_for_target_df} --- \n")
    logger.info(f"\n ---UPDATED child_id_list_for_target_df : {child_id_list_for_target_df} --- \n")


async def update_mapping_json_for_reference(inter_entity_placement, tree_for_target_df, mapping_json):
    # This is the code to copy all the attribute to where this entity is being referenced
    for child_entity_id, data in inter_entity_placement.items():
        # if data["Placement"] and data["Placement"] == 'Reference':
        if data["Placement"]:
            # This reference so adding it to top most parent - in LIF
            ancestor_list = await find_ancestors(
                tree_for_target_df, child_entity_id, inter_entity_placement=inter_entity_placement
            )
            logger.info(f"child_entity_id: {child_entity_id}")
            logger.info(f"parent_entity_id: {data['ParentEntityId']}")
            logger.info(f"placement is reference : ancestor list {ancestor_list}")

            attribute_data_to_copy = None
            children_data_to_copy = None
            if len(ancestor_list) > 0:
                if ancestor_list[0] == data["ParentEntityId"]:
                    # If only ancestor is the current parent then create entity at the root level
                    # tree_for_target_df[child_entity_id]=[]

                    # attribute_data_to_copy = mapping_json[child_entity_id]['attributes']
                    # if data["Placement"] == EntityPlacementType.Embedded:
                    #     children_data_to_copy = mapping_json[child_entity_id]['children']
                    continue

                else:
                    # tree_for_target_df[ancestor_list[0]].append(child_entity_id)
                    ancestor_list.append(child_entity_id)
                    target_json = mapping_json[ancestor_list[0]]
                    target_found = False
                    for ancestor in ancestor_list[1:]:
                        logger.info(f"ancestor:{ancestor}")
                        for child in target_json["children"]:
                            if child_entity_id == child["id"]:
                                logger.info(f"child['id']:{child['id']}")
                                target_json = child
                                attribute_data_to_copy = child["attributes"]
                                if data["Placement"] == EntityPlacementType.Embedded:
                                    children_data_to_copy = child["children"]
                                break
            else:
                attribute_data_to_copy = mapping_json[child_entity_id]["attributes"]
                if data["Placement"] == EntityPlacementType.Embedded:
                    children_data_to_copy = mapping_json[child_entity_id]["children"]

            logger.info(f"data_to_copy: {attribute_data_to_copy}")
            if attribute_data_to_copy:
                logger.info(f"parent_entity_id: {data['ParentEntityId']}")
                ancestor_for_parent_id = await find_ancestors(
                    tree_for_target_df, data["ParentEntityId"], inter_entity_placement=inter_entity_placement
                )
                logger.info(f"ancestor_for_parent_id: {ancestor_for_parent_id}")
                ancestor_for_parent_id.append(data["ParentEntityId"])
                # Adding child entity id to get the final JSON and confirm the child is there in
                ancestor_for_parent_id.append(child_entity_id)
                logger.info(f" final ancestor_for_parent_id: {ancestor_for_parent_id}")
                target_json = mapping_json[ancestor_for_parent_id[0]]
                target_found = False
                for ancestor in ancestor_for_parent_id[1:]:
                    logger.info(f"ancestor:{ancestor}")
                    for child in target_json["children"]:
                        if ancestor == child["id"]:
                            logger.info(f"child['id']:{child['id']}")
                            target_json = child
                            break
                    if ancestor == child_entity_id:
                        logger.info("Target found")
                        target_found = True
                logger.info(f"target_found : {target_found}")

                if target_found:
                    logger.info(f"Target Json found : {target_json}")
                    target_json["attributes"] = attribute_data_to_copy
                    if data["Placement"] == EntityPlacementType.Embedded:
                        target_json["children"] = children_data_to_copy


async def generate_jinja(
    session: AsyncSession,
    source_data_model_name: str,
    source_data_model_version: str,
    target_data_model_name: str,
    target_data_model_version: str,
):
    source_data_model_id = await get_data_model_id_by_name_and_version(
        session=session, name=source_data_model_name, version=source_data_model_version
    )
    target_data_model_id = await get_data_model_id_by_name_and_version(
        session=session, name=target_data_model_name, version=target_data_model_version
    )

    source_data_model_id_list = await get_base_model_ids(session=session, data_model_id=source_data_model_id)
    target_data_model_id_list = await get_base_model_ids(session=session, data_model_id=target_data_model_id)
    entity_data_model_id_list = []
    entity_data_model_id_list.extend(source_data_model_id_list)
    entity_data_model_id_list.extend(target_data_model_id_list)

    logger.info(f"source_data_model_id_list : {source_data_model_id_list}")
    logger.info(f"target_data_model_id_list : {target_data_model_id_list}")
    logger.info(f"entity_data_model_id_list : {entity_data_model_id_list}")

    # Alias for models to avoid conflicts
    tg = TransformationGroup
    ta = TransformationAttribute
    t = Transformation
    a = Attribute
    eaa = EntityAttributeAssociation
    e = Entity
    d = DataModel

    # Build the query
    query = (
        select(
            t.Id.label("transformation_id"),
            tg.SourceDataModelId,
            tg.TargetDataModelId,
            t.Name,
            t.Alignment,
            t.Expression,
            t.ExpressionLanguage,
            ta.AttributeId,
            ta.AttributeType,
            a.Name.label("attribute_name"),
            a.DataType.label("attribute_data_type"),
            a.Array.label("is_attribute_array"),
            eaa.EntityId,
            e.Name.label("entity_name"),
            e.Array.label("is_entity_array"),
            d.Name.label("data_model_name"),
        )
        .join(tg, tg.Id == t.TransformationGroupId)
        .join(ta, t.Id == ta.TransformationId)
        .join(a, a.Id == ta.AttributeId)
        .join(eaa, eaa.AttributeId == ta.AttributeId)
        .join(e, and_(e.Id == eaa.EntityId, e.DataModelId.in_(entity_data_model_id_list)))
        .join(
            d,
            or_(
                (d.Id == tg.SourceDataModelId) & (ta.AttributeType == "Source"),
                (d.Id == tg.TargetDataModelId) & (ta.AttributeType == "Target"),
            ),
        )
        .where(
            t.Expression != "",
            tg.SourceDataModelId == source_data_model_id,
            tg.TargetDataModelId == target_data_model_id,
        )
        .order_by(t.Id)
    )

    execution = await session.execute(query)
    result = execution.fetchall()
    column_names = result[0]._fields if result else []

    # Convert the result into a pandas DataFrame
    df = pd.DataFrame(result, columns=column_names)

    if len(df) == 0:
        return {
            "message": f"There are no transformation defined for source {source_data_model_name}, version {source_data_model_version} to target {target_data_model_name}, version {target_data_model_version}"
        }

    # logger.info(df)
    # logger.info(df)  # Should print: <class 'pandas.core.frame.DataFrame'>
    logger.info(df.columns)  # Should include 'AttributeType'
    df_source = df[df["AttributeType"] == "Source"]
    df_target = df[df["AttributeType"] == "Target"]

    df_entity = await get_all_entity_data_frame(session=session)

    distinctEntityIds = df_target["EntityId"].unique().tolist()
    logger.info(f"distinctEntityId : {distinctEntityIds}")
    # distinctEntityNames = []
    # for id in distinctEntityIds:
    #     entity_name = (df_entity[df_entity['Id'] == id])["Name"].unique().tolist()[0]
    #     distinctEntityNames.append(entity_name)

    in_clause = ", ".join(map(str, distinctEntityIds))
    in_clause = f"({in_clause})"
    logger.info(f"query_filter : {in_clause}")

    # Creating tree and top level entities for the given LIF entities.
    query = (
        select(EntityAssociation.ParentEntityId, EntityAssociation.ChildEntityId)
        .where(
            EntityAssociation.ParentEntityId.in_(distinctEntityIds),  # IN clause for ParentEntityId
            EntityAssociation.Relationship.is_(None),  # Relationship is null
            EntityAssociation.Deleted == False,
        )
        .order_by(EntityAssociation.ParentEntityId)
    )

    result = await session.execute(query)
    rows = result.fetchall()
    logger.info("--- Getting data tree for target data model entities --")
    (
        tree_for_target_df,
        parent_id_list_for_target_df,
        child_id_list_for_target_df,
        top_level_parents_for_target_df,
        target_tree_with_entity_names,
        target_top_level_entity_names,
    ) = await get_complete_entity_tree(rows=rows, df_entity=df_entity, distinctEntityIds=distinctEntityIds)

    # Adding remaining entity ids to top level parents as we do not have child for those in the given transformation data.
    for entity_id in distinctEntityIds:
        if entity_id not in parent_id_list_for_target_df and entity_id not in child_id_list_for_target_df:
            top_level_parents_for_target_df.append(entity_id)
    logger.info(f"top_level_parents_for_target_df : {top_level_parents_for_target_df}")

    target_top_level_entity_names = []
    for entity_id in top_level_parents_for_target_df:
        parent_entity_name = (df_target[df_target["EntityId"] == entity_id])["entity_name"].unique().tolist()[0]
        target_top_level_entity_names.append(parent_entity_name)
    logger.info(f"target_top_level_entity_names : {target_top_level_entity_names}")

    logger.info("--- Getting data tree for all entities --")
    parent_id_query = (
        select(EntityAssociation.ParentEntityId, EntityAssociation.ChildEntityId)
        .join(Entity, Entity.Id == EntityAssociation.ParentEntityId)
        .where(EntityAssociation.Deleted == False)
        .where(EntityAssociation.Relationship.is_(None))
        .where(Entity.DataModelId.in_(target_data_model_id_list))
    )
    result = await session.execute(parent_id_query)
    rows = result.fetchall()
    logger.info(f"Rows for all entities : {rows}")
    (
        tree_for_all_entities,
        parent_id_list_for_all_entities,
        child_id_list_for_all_entities,
        top_level_parents_for_all_entities,
        complete_tree_with_entity_names,
        complete_top_level_entity_names,
    ) = await get_complete_entity_tree(rows=rows, df_entity=df_entity)

    extended_subtree = await extend_subtree(tree_for_all_entities, tree_for_target_df, distinctEntityIds)
    logger.info(f"\n ---extended_subtree : {extended_subtree} --- \n")
    logger.info(f"\n ---tree_for_target_df : {tree_for_target_df} --- \n")

    # Checking if parent in the target tree is a child to any entity in the target tree, if yes then add parent to that entity's child list
    for parent, child_list in tree_for_target_df.items():
        if parent in child_id_list_for_all_entities:
            parent_ancestors = await find_ancestors(tree=tree_for_all_entities, child=parent)
            parent_ancestors.reverse()  # Reversing so that we can add child to immediate parent
            for ancestor in parent_ancestors:
                if ancestor in tree_for_target_df:
                    if parent in tree_for_target_df[ancestor]:
                        logger.info("Child already in parent list.")
                        break
                    else:
                        logger.info("Ancestor is in tree..")
                        tree_for_target_df[ancestor].append(parent)
                        break
    logger.info(f"\n  ............... tree_for_target_df : {tree_for_target_df} --- \n")

    for parent, child_list in tree_for_target_df.items():
        if parent not in parent_id_list_for_target_df:
            parent_id_list_for_target_df.append(parent)
        for child in child_list:
            if child not in child_id_list_for_target_df:
                child_id_list_for_target_df.append(child)
    logger.info(f"\n --- UPDATED parent_id_list_for_target_df : {parent_id_list_for_target_df} --- \n")
    logger.info(f"\n ---UPDATED child_id_list_for_target_df : {child_id_list_for_target_df} --- \n")

    top_level_parents_for_target_df = [p for p in parent_id_list_for_target_df if p not in child_id_list_for_target_df]
    logger.info(f"\n ---UPDATED top_level_parents_for_target_df : {top_level_parents_for_target_df} --- \n")

    # Getting inter-entity link and checking if any top level parent is a child for any other top level
    query = (
        select(
            EntityAssociation.ParentEntityId,
            EntityAssociation.ChildEntityId,
            EntityAssociation.Relationship,
            EntityAssociation.Placement,
        )
        .where(
            EntityAssociation.Relationship.is_not(None),  # Relationship is not null
            EntityAssociation.Deleted == False,
        )
        .order_by(EntityAssociation.ParentEntityId)
    )
    result = await session.execute(query)
    result_inter_entity = result.fetchall()
    column_names = result_inter_entity[0]._fields if result_inter_entity else []
    df_inter_entity = pd.DataFrame(result_inter_entity, columns=column_names)
    inter_entity_placement = {}
    for top_level_parent in top_level_parents_for_target_df:
        inter_entity_parent_list = df_inter_entity[df_inter_entity["ChildEntityId"] == top_level_parent]
        for index, row in inter_entity_parent_list.iterrows():
            parent_id = row["ParentEntityId"]
            child_id = row["ChildEntityId"]
            relationship = row["Relationship"]
            placement = row["Placement"]
            # logger.info(f"parent_entity : {parent_id}")
            if parent_id in top_level_parents_for_target_df:
                if top_level_parent not in tree_for_target_df[parent_id]:
                    tree_for_target_df[parent_id].append(top_level_parent)
                    top_level_parents_for_target_df.remove(top_level_parent)
                    inter_entity_placement[child_id] = {
                        "ParentEntityId": parent_id,
                        "Relationship": relationship,
                        "Placement": placement,
                    }

    logger.info(f"\n  ************* tree_for_target_df : {tree_for_target_df} --- \n")
    logger.info(f"\n  ************* inter_entity_placement : {inter_entity_placement} --- \n")
    logger.info(f"\n ---UPDATED top_level_parents_for_target_df : {top_level_parents_for_target_df} --- \n")

    for parent, child_list in tree_for_target_df.items():
        if parent not in parent_id_list_for_target_df:
            parent_id_list_for_target_df.append(parent)
        for child in child_list:
            if child not in child_id_list_for_target_df:
                child_id_list_for_target_df.append(child)
    logger.info(f"\n --- UPDATED parent_id_list_for_target_df : {parent_id_list_for_target_df} --- \n")
    logger.info(f"\n ---UPDATED child_id_list_for_target_df : {child_id_list_for_target_df} --- \n")

    # -------------------------- testing ------------------------------------
    tree_for_target_df_for_test = tree_for_target_df.copy()
    for parent, child_list in tree_for_target_df_for_test.items():
        for child in child_list:
            inter_entity_parent_list = df_inter_entity[df_inter_entity["ChildEntityId"] == child]
            for index, row in inter_entity_parent_list.iterrows():
                parent_id = row["ParentEntityId"]
                relationship = row["Relationship"]
                placement = row["Placement"]
                # logger.info(f"parent_entity : {parent_id}")
                if parent_id in tree_for_target_df_for_test and child not in tree_for_target_df_for_test[parent_id]:
                    tree_for_target_df_for_test[parent_id].append(child)
                    inter_entity_placement[child] = {
                        "ParentEntityId": parent_id,
                        "Relationship": relationship,
                        "Placement": placement,
                    }
    logger.info(f"\n  ***--****--***--*** tree_for_target_df_for_test : {tree_for_target_df_for_test} --- \n")
    logger.info(f"\n  ***--****--***--*** inter_entity_placement : {inter_entity_placement} --- \n")
    # ----------------------------------------------------------------------------

    # As we have LIF 1.0 has different schema than entity Associations, we need to update the target tree based on LIF 1.0 schema, if LIF 1.0 is target data model or it is a base mode for given target model.
    lif_v1_Id = await get_data_model_id_by_name_and_version(session=session, name="LIF", version="1.0")
    if lif_v1_Id in target_data_model_id_list:
        await update_schema_for_lif_1(
            session=session,
            tree_for_target_df=tree_for_target_df,
            child_id_list_for_target_df=child_id_list_for_target_df,
            parent_id_list_for_target_df=parent_id_list_for_target_df,
            lif_v1_Id=lif_v1_Id,
        )

    root_entities = []
    for child_entity_id, data in inter_entity_placement.items():
        if data["Placement"] and data["Placement"] == "Reference":
            # This reference so adding it to top most parent - in LIF
            ancestor_list = await find_ancestors(tree_for_target_df, child_entity_id)
            logger.info(f"placement is reference : ancestor list {ancestor_list}")
            logger.info(f" data['ParentEntityId']:  {data['ParentEntityId']}")
            if len(ancestor_list) > 0:
                if ancestor_list[0] == data["ParentEntityId"]:
                    # tree_for_target_df[ancestor_list[0]].remove(child_entity_id)
                    # if child_entity_id not in top_level_parents_for_target_df:
                    #     # If only ancestor is the current parent then create entity at the root level
                    #     logger.info(f" data['ParentEntityId']:  { data['ParentEntityId']}")
                    #     # tree_for_target_df[child_entity_id]=[]
                    if child_entity_id not in top_level_parents_for_target_df:
                        top_level_parents_for_target_df.append(child_entity_id)
                    root_entities.append(child_entity_id)
                else:
                    if child_entity_id not in tree_for_target_df[ancestor_list[0]]:
                        tree_for_target_df[ancestor_list[0]].append(child_entity_id)
                    # tree_for_target_df[ancestor_list[-1]].remove(child_entity_id)

    logger.info(f"\n  *************&&&&&&&&&&&&&&&& tree_for_target_df : {tree_for_target_df} --- \n")
    logger.info(f"\n  *************&&&&&&&&&&&&&&&& inter_entity_placement : {inter_entity_placement} --- \n")

    # processing any inter-entity from the data model if data model is extension
    if len(target_data_model_id_list) > 1:
        # this means the target is extension
        parent_id_query = (
            select(
                EntityAssociation.ParentEntityId,
                EntityAssociation.ChildEntityId,
                EntityAssociation.Relationship,
                EntityAssociation.Placement,
            )
            .where(EntityAssociation.Deleted == False)
            .where(EntityAssociation.ExtendedByDataModelId == target_data_model_id)
        )
        result = await session.execute(parent_id_query)
        result_inter_entity = result.fetchall()
        column_names = result_inter_entity[0]._fields if result_inter_entity else []
        df_target_inter_entity = pd.DataFrame(result_inter_entity, columns=column_names)
        for index, row in df_target_inter_entity.iterrows():
            logger.info(f"row : {row}")
            parent_id = row["ParentEntityId"]
            child_id = row["ChildEntityId"]
            relationship = row["Relationship"]
            placement = row["Placement"]
            logger.info(f"parent_entity : {parent_id}")
            if parent_id in tree_for_target_df and child_id not in tree_for_target_df[parent_id]:
                tree_for_target_df[parent_id].append(child_id)
                child_id_list_for_target_df.append(child)
                if child_id in top_level_parents_for_target_df:
                    top_level_parents_for_target_df.remove(child_id)
                inter_entity_placement[child_id] = {
                    "ParentEntityId": parent_id,
                    "Relationship": relationship,
                    "Placement": placement,
                }
    logger.info(f"\n  ========================== tree_for_target_df : {tree_for_target_df} ================= \n")
    logger.info(
        f"\n  ========================== inter_entity_placement : {inter_entity_placement} ================= \n"
    )

    for parent, child_list in tree_for_target_df.items():
        if parent not in parent_id_list_for_target_df:
            parent_id_list_for_target_df.append(parent)
        for child in child_list:
            if child not in child_id_list_for_target_df:
                child_id_list_for_target_df.append(child)
    logger.info(f"\n --- UPDATED parent_id_list_for_target_df : {parent_id_list_for_target_df} --- \n")
    logger.info(f"\n ---UPDATED child_id_list_for_target_df : {child_id_list_for_target_df} --- \n")

    top_level_parents_for_target_df = [p for p in parent_id_list_for_target_df if p not in child_id_list_for_target_df]
    logger.info(f"\n ---UPDATED top_level_parents_for_target_df : {top_level_parents_for_target_df} --- \n")

    paths_for_all_children, paths_for_all_children_with_name = await create_paths_dict(
        tree=tree_for_target_df, inter_entity_placement=inter_entity_placement, df_entity=df_entity
    )
    logger.info(f"paths_for_all_children :{paths_for_all_children}")
    logger.info(f"paths_for_all_children_with_name :{paths_for_all_children_with_name}")

    # tree_for_target_df = {131: [135, 136, 137, 133], 291: [278, 139, 223], 139: [140, 141, 135, 131, 223], 223: [225, 226], 133: [134]}

    # Creating mapping json based on target tree
    mapping_json = {}
    # Get top-level roots (entities without parents)
    all_children = {child for children in tree_for_target_df.values() for child in children}
    logger.info(f"all_children : {all_children}")
    roots = [node for node in tree_for_target_df if node not in all_children]
    logger.info(f"roots : {roots}")
    if len(root_entities) != 0:
        roots.extend(root_entities)
    logger.info(f"roots : {roots}")
    logger.info(f"*************** inter_entity_placement : {inter_entity_placement}")
    # Build the JSON structure
    mapping_json = {
        root: await build_tree(tree_for_target_df, root, parent=None, inter_entity_placement=inter_entity_placement)
        for root in roots
    }
    logger.info(f"*************** mapping_json : {mapping_json}")

    logger.info(f"\n --- mapping_json : {mapping_json} --- \n")
    # ---------------------------------------------------------------

    schema = {}
    schema["version"] = 2

    # Creating sources
    logger.info("Processing source tables")
    schema["sources"] = {}
    visited_sources = {}
    for index, row in df_source.iterrows():
        # logger.info(" ---------------------- ")

        # table_name =  row["data_model_name"]+ "_" +row["entity_name"]
        # column_name = row["attribute_name"]
        # TODO : Add standard name with resource_name like CASE_CompetencyFramework
        table_name = row["data_model_name"].replace(" ", "")
        table_name += "_" + row["data_model_name"].replace(" ", "")
        column_name = row["entity_name"].replace(" ", "")

        # logger.info(f"table_name : {table_name}")
        # logger.info(f"column_name : {column_name}")
        if table_name in visited_sources:
            # logger.info("Table is in the visited list.")
            table_details = visited_sources.get(table_name)
        else:
            # logger.info("Table is not visited.")
            table_details = {
                "file": "",  # this is needed (for now) to prevent an earthmover compilation error
                "optional": True,  # these are the columns available in the sample HROpen person record (some are nested objects/arrays)}
            }
            table_details["columns"] = []

        if column_name not in table_details["columns"]:
            table_details["columns"].append(column_name)
        visited_sources[table_name] = table_details
    schema["sources"] = visited_sources
    logger.info("Source schema : -----")
    logger.info(schema)

    # Updating transformation creation:
    # Creating transformations
    logger.info(" \n\n\t ***************** Processing target tables ************** \n\n")
    schema["transformations"] = {}
    visited_target = {}
    get_mapping = {}
    get_operation_found = []
    for index, row in df_target.iterrows():
        logger.info(" --------------------------------- ")
        logger.info(row)
        target_table_name = row["data_model_name"] + "_" + row["entity_name"]
        # target_table_name =  row["entity_name"]
        target_attribute_name = row["attribute_name"]
        transformation_id = row["transformation_id"]
        target_entity_name = row["entity_name"]
        target_expression = row["Expression"]
        target_entity_id = row["EntityId"]

        target_attribute_data_type = row["attribute_data_type"]
        is_target_attribute_array = row["is_attribute_array"]
        is_target_entity_array = row["is_entity_array"]

        # Getting ancestors to have jinja instruction at root level
        target_ancestors = await find_ancestors(tree=tree_for_all_entities, child=target_entity_id)
        logger.info(f"target_entity : {target_entity_name} and ancestors : {target_ancestors}")
        immediate_parent_name = None
        if len(target_ancestors) > 0:
            root_entity_name = (
                (df_entity[df_entity["Id"] == target_ancestors[0]])["Name"].unique().tolist()[0]
            )  # top most root
            if len(target_ancestors) > 1:
                # Immediate parent after root - going one level below
                immediate_parent_name = (df_entity[df_entity["Id"] == target_ancestors[1]])["Name"].unique().tolist()[0]
            target_table_name = row["data_model_name"] + "_" + root_entity_name
        filtered_source_data = df_source[df_source["transformation_id"] == transformation_id]
        source_data = filtered_source_data.iloc[0]
        # source_table_name =  source_data["data_model_name"]+ "_" +source_data["entity_name"]
        # source_column_name = source_data["attribute_name"]

        source_table_name = (
            source_data["data_model_name"].replace(" ", "") + "_" + source_data["data_model_name"].replace(" ", "")
        )
        source_entity_name = source_data["entity_name"].replace(" ", "")
        source_attribute_name = source_data["attribute_name"]
        source_attribute_data_type = source_data["attribute_data_type"]
        logger.info(f"source_attribute_data_type : {source_attribute_data_type}")
        logger.info(f"source_entity_name : {source_entity_name}")
        logger.info(f"source_attribute_name : {source_attribute_name}")
        is_source_attribute_array = source_data["is_attribute_array"]
        is_source_entity_array = source_data["is_entity_array"]

        await create_get_mapping_v3(
            mapping_json=mapping_json,
            target_entity_id=target_entity_id,
            target_attribute_name=target_attribute_name,
            source_attribute_name=source_attribute_name,
            source_entity_name=source_entity_name,
            tree_for_target_df=tree_for_target_df,
            target_expression=target_expression,
            target_attribute_data_type=target_attribute_data_type,
            is_target_attribute_array=is_target_attribute_array,
            is_target_entity_array=is_target_entity_array,
            source_attribute_data_type=source_attribute_data_type,
            is_source_attribute_array=is_source_attribute_array,
            is_source_entity_array=is_source_entity_array,
            inter_entity_placement=inter_entity_placement,
            top_level_parents_for_target_df=top_level_parents_for_target_df,
            paths_for_all_children=paths_for_all_children,
            paths_for_all_children_with_name=paths_for_all_children_with_name,
        )

    logger.info(f" ------------------ mapping json -------------- : {mapping_json}")

    await update_mapping_json_for_reference(
        inter_entity_placement=inter_entity_placement, tree_for_target_df=tree_for_target_df, mapping_json=mapping_json
    )

    # if 'get'in target_expression:
    #     create_get_mapping_v2(
    #         mapping_json=mapping_json,
    #         target_entity_id=target_entity_id,
    #         target_attribute_name=target_attribute_name,
    #         source_attribute_name=source_attribute_name,
    #         source_entity_name=source_entity_name,
    #         tree_for_target_df=tree_for_target_df,
    #         target_expression=target_expression
    #     )

    logger.info(f"Updated mapping_json : {mapping_json}")

    logger.info(" \n\n\t ***************** Processing target tables ************** \n\n")
    schema["transformations"] = {}
    visited_target_v2 = {}
    for parent, child_dict in mapping_json.items():
        parent_entity_name = (df_entity[df_entity["Id"] == parent])["Name"].unique().tolist()[0]
        target_table_name = child_dict["data_model"] + "_" + parent_entity_name
        source_table_name = source_data_model_name.replace(" ", "") + "_" + source_data_model_name.replace(" ", "")
        logger.info("------------------------------------------------------------")
        logger.info(f"parent : {parent}")
        logger.info(f"parent_entity_name : {parent_entity_name}")
        logger.info(f"target_table_name : {target_table_name}")
        logger.info(f"source_table_name : {source_table_name}")

        table_details = {"source": "$sources." + source_table_name}
        table_details["operations"] = []
        # TODO: Creating default operations but we need to configure it for columns.
        # Define operations
        operation_add_columns = {"operation": "add_columns", "columns": {}}
        operation_keep_columns = {"operation": "keep_columns", "columns": []}

        await jinja_creation(
            top_level_json=child_dict,
            visited_dict_add_columns=operation_add_columns["columns"],
            visited_dict_keep_column=operation_keep_columns["columns"],
            df_entity=df_entity,
        )

        table_details["operations"].append(operation_add_columns)
        table_details["operations"].append(operation_keep_columns)
        logger.info(f"table_details : {table_details}")
        visited_target_v2[target_table_name] = table_details
    logger.info(f"visited_target_v2 : {visited_target_v2}")

    schema["transformations"] = visited_target_v2
    logger.info("--------------------------")
    logger.info(schema)

    return schema

    # # Creating mapping json based on target tree
    # mapping_json = {}
    # # Get top-level roots (entities without parents)
    # all_children = {child for children in tree_for_target_df.values() for child in children}
    # roots = [node for node in tree_for_target_df if node not in all_children]

    # # Build the JSON structure
    # mapping_json = {root: await build_tree(tree_for_target_df, root) for root in roots}

    # logger.info(f"\n --- mapping_json : {mapping_json} --- \n")
    # #---------------------------------------------------------------

    # schema={}
    # schema["version"] = 2

    # # Creating sources
    # logger.info("Processing source tables")
    # schema["sources"] = {}
    # visited_sources = {}
    # for index,row in df_source.iterrows():
    #     # logger.info(" ---------------------- ")

    #     # table_name =  row["data_model_name"]+ "_" +row["entity_name"]
    #     # column_name = row["attribute_name"]
    #     # TODO : Add standard name with resource_name like CASE_CompetencyFramework
    #     table_name =  row["data_model_name"].replace(" ","")
    #     table_name += "_" + row["data_model_name"].replace(" ","")
    #     column_name = row["entity_name"].replace(" ","")

    #     # logger.info(f"table_name : {table_name}")
    #     # logger.info(f"column_name : {column_name}")
    #     if table_name in visited_sources:
    #         # logger.info("Table is in the visited list.")
    #         table_details = visited_sources.get(table_name)
    #     else:
    #         # logger.info("Table is not visited.")
    #         table_details = { "file": "", # this is needed (for now) to prevent an earthmover compilation error
    #                         "optional": True # these are the columns available in the sample HROpen person record (some are nested objects/arrays)}
    #                         }
    #         table_details["columns"] = []

    #     if column_name not in  table_details["columns"]:
    #         table_details["columns"].append(column_name)
    #     visited_sources[table_name] = table_details
    # schema["sources"] = visited_sources
    # logger.info("Source schema : -----")
    # logger.info(schema)

    # # Updating transformation creation:
    # # Creating transformations
    # logger.info(" \n\n\t ***************** Processing target tables ************** \n\n")
    # schema["transformations"] = {}
    # visited_target = {}
    # get_mapping = {}
    # get_operation_found=[]
    # for index,row in df_target.iterrows():
    #     # logger.info(" ---------------------- ")
    #     target_table_name =  row["data_model_name"]+ "_" +row["entity_name"]
    #     # target_table_name =  row["entity_name"]
    #     target_attribute_name = row["attribute_name"]
    #     transformation_id = row["transformation_id"]
    #     target_entity_name = row["entity_name"]
    #     target_expression = row["Expression"]
    #     target_entity_id = row["EntityId"]

    #     # Getting ancestors to have jinja instruction at root level
    #     target_ancestors = await find_ancestors(tree=tree_for_all_entities,child=target_entity_id)
    #     logger.info(f"target_entity : {target_entity_name} and ancestors : {target_ancestors}")
    #     immediate_parent_name = None
    #     if len(target_ancestors) > 0:
    #         root_entity_name = (df_entity[df_entity['Id'] == target_ancestors[0]])["Name"].unique().tolist()[0] # top most root
    #         if len(target_ancestors) > 1:
    #             # Immediate parent after root - going one level below
    #             immediate_parent_name = (df_entity[df_entity['Id'] == target_ancestors[1]])["Name"].unique().tolist()[0]
    #         target_table_name = row["data_model_name"]+ "_" + root_entity_name
    #     filtered_source_data = df_source[df_source["transformation_id"] == transformation_id]
    #     source_data = filtered_source_data.iloc[0]
    #     # source_table_name =  source_data["data_model_name"]+ "_" +source_data["entity_name"]
    #     # source_column_name = source_data["attribute_name"]

    #     source_table_name =  source_data["data_model_name"].replace(" ","") + "_" + source_data["data_model_name"].replace(" ","")
    #     source_entity_name = source_data["entity_name"].replace(" ","")
    #     source_attribute_name = source_data["attribute_name"]

    #     # if 'get'in target_expression:
    #     await create_get_mapping_v2(
    #             mapping_json=mapping_json,
    #             target_entity_id=target_entity_id,
    #             target_attribute_name=target_attribute_name,
    #             source_attribute_name=source_attribute_name,
    #             source_entity_name=source_entity_name,
    #             tree_for_target_df=tree_for_target_df,
    #             target_expression=target_expression
    #         )

    # logger.info(f"Updated mapping_json : {mapping_json}")

    # logger.info(" \n\n\t ***************** Processing target tables ************** \n\n")
    # schema["transformations"] = {}
    # visited_target_v2 = {}
    # for parent, child_dict in mapping_json.items():
    #     parent_entity_name = (df_entity[df_entity['Id'] == parent])["Name"].unique().tolist()[0]
    #     target_table_name = child_dict["data_model"] + "_" + parent_entity_name
    #     source_table_name =  source_data_model_name.replace(" ","") + "_" + source_data_model_name.replace(" ","")
    #     logger.info("------------------------------------------------------------")
    #     logger.info(f"parent : {parent}")
    #     logger.info(f"parent_entity_name : {parent_entity_name}")
    #     logger.info(f"target_table_name : {target_table_name}")
    #     logger.info(f"source_table_name : {source_table_name}")

    #     table_details ={"source": "$sources."+source_table_name}
    #     table_details["operations"] = []
    #     # TODO: Creating default operations but we need to configure it for columns.
    #     # Define operations
    #     operation_add_columns = {"operation": "add_columns", "columns": {}}
    #     operation_keep_columns = {"operation": "keep_columns", "columns": []}

    #     await jinja_creation_v6(
    #         top_level_json=child_dict,
    #         visited_dict_add_columns=operation_add_columns["columns"],
    #         visited_dict_keep_column=operation_keep_columns["columns"],
    #         df_entity=df_entity
    #     )

    #     table_details["operations"].append(operation_add_columns)
    #     table_details["operations"].append(operation_keep_columns)
    #     logger.info(f"table_details : {table_details}")
    #     visited_target_v2[target_table_name] = table_details
    # logger.info(f"visited_target_v2 : {visited_target_v2}")

    # schema["transformations"] = visited_target_v2
    # logger.info("--------------------------")
    # logger.info(schema)
