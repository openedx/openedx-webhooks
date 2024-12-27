"""
Functions for working with GitHub projects with the GraphQL API.
"""

from typing import Set

from glom import glom

from openedx_webhooks.tasks import logger
from openedx_webhooks.types import GhProject, PrDict, PrId
from openedx_webhooks.utils import graphql_query

# The name of the query is used by FakeGitHub while testing.

PROJECTS_FOR_PR = """\
query ProjectsForPr (
  $owner: String!
  $name: String!
  $number: Int!
) {
  repository (owner: $owner, name: $name) {
    pullRequest (number: $number) {
      projectItems (first: 100) {
        nodes {
          project {
            number
            owner {
              ... on Organization {
                login
              }
            }
          }
        }
      }
    }
  }
}
"""


def pull_request_projects(pr: PrDict) -> Set[GhProject]:
    """Return the projects this PR is in.

    The projects are expressed as sets of tuples with owning org and number:
    {("openedx", 19)}

    """
    variables = glom(pr, {
        "owner": "base.repo.owner.login",
        "name": "base.repo.name",
        "number": "number"
    })
    logger.debug(f"Getting projects for PR: {variables}")
    data = graphql_query(query=PROJECTS_FOR_PR, variables=variables)
    projects = glom(
        data,
        (
            "repository.pullRequest.projectItems.nodes",
            [
                {"org": "project.owner.login", "number": "project.number"}
            ]
        )
    )
    # I can't figure out how to get glom to make a tuple directly...
    return {(p["org"], p["number"]) for p in projects}


ORG_PROJECT_ID = """\
query OrgProjectId (
  $owner: String!
  $number: Int!
) {
  organization (login: $owner) {
    projectV2 (number: $number) {
      id
    }
  }
}
"""

ADD_PROJECT_ITEM = """\
mutation AddProjectItem (
  $projectId: ID!
  $prNodeId: ID!
) {
  addProjectV2ItemById (input: {projectId: $projectId, contentId: $prNodeId}) {
    item {
      id
    }
  }
}
"""


def add_pull_request_to_project(prid: PrId, pr_node_id: str, project: GhProject) -> None:
    """Add a pull request to a project.

    The project is a tuple: (orgname, number)
    """
    logger.info(f"Adding PR {prid.full_name}#{prid.number} to project {project}")
    # Find the project id.
    variables = {"owner": project[0], "number": project[1]}
    data = graphql_query(query=ORG_PROJECT_ID, variables=variables)
    proj_id = glom(data, "organization.projectV2.id")

    # Add the pull request.
    variables = {"projectId": proj_id, "prNodeId": pr_node_id}
    data = graphql_query(query=ADD_PROJECT_ITEM, variables=variables)


ORG_PROJECT_METADATA = """\
query ($orgname: String!, $number: Int!) {
  organization(login: $orgname) {
    projectV2(number: $number) {
      id
      fields(first: 100) {
        nodes {
          ... on ProjectV2FieldCommon {
            id
            name
            dataType
          }
          ... on ProjectV2SingleSelectField {
            options {
              id
              name
            }
          }
        }
      }
    }
  }
}
"""

UPDATE_PROJECT_ITEM = """\
mutation UpdateProjectItem (
  $projectId: ID!
  $itemId: ID!
  $fieldId: ID!
  $value: {fieldType}
) {
  updateProjectV2ItemFieldValue (input: {projectId: $projectId, contentId: $prNodeId}) {
    item {
      id
    }
  }
}
"""


def update_project_custom_field(field_name: str, field_value, itemId: str, project: GhProject) -> None:
    """Add a pull request to a project.

    The project is a tuple: (orgname, number)
    """
    logger.info(f"Updating project {project} field {field_name} to {field_value}")
    # Find the project metadata.
    variables = {"orgname": project[0], "number": project[1]}
    data = graphql_query(query=ORG_PROJECT_METADATA, variables=variables)
    data = glom(data, {"id": "organization.projectV2.id", "fields": "organization.projectV2.fields.nodes"})

    target_field = None
    for field in data["fields"]:
        if field["name"] == field_name:
            target_field = field
            break
    else:
        logger.error(f"Could not find field with name: {field_name} in project: {project}")
        return

    # Update field value
    variables = {"projectId": data["id"], "fieldId": target_field["id"], "itemId": "< rowId >"}
    data = graphql_query(query=UPDATE_PROJECT_ITEM, variables=variables)


if __name__ == '__main__':
    update_project_custom_field('Date opened', '1', ('openedx', 19))
