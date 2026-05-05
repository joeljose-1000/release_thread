ISSUE_BASIC = """
query IssueBasic($id: String!) {
  issue(id: $id) {
    identifier
    title
    url
    assignee {
      name
      displayName
    }
  }
}
"""

ISSUE_WITH_STATE = """
query IssueWithState($id: String!) {
  issue(id: $id) {
    identifier
    title
    url
    assignee {
      name
      displayName
    }
    state {
      name
    }
  }
}
"""
