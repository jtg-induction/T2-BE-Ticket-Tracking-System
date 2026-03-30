class ProjectMessages:
    """
    User-facing error and validation messages for Project operations.
    """

    # Permissions & Roles
    ADMIN_REQUIRED = "Admin rights required."
    OWNER_ONLY_TRANSFER = "Only the owner can transfer ownership."
    PROMOTION_DENIED = "No permission to promote."
    DEMOTION_DENIED = "Only the owner can demote admins."
    PERMISSION_DENIED = "Permission denied."
    OWNER_CANNOT_LEAVE = "Owner cannot leave without transferring ownership."
    INVALID_ROLE = "Invalid role."

    # Invitations
    INVITE_SENT = "Invitation sent."
    JOINED_SUCCESS = "Joined successfully."
    INVITE_REJECTED = "Invitation rejected."
    INVITE_EXISTS = "Invitation already exists for this user."
    INVALID_TOKEN = "Invalid token"
    NOT_YOUR_INVITE = "This invitation is not for you."
    INVITE_EXPIRED = "Expired or invalid invitation."
    INVITE_NOT_FOUND = "Invitation not found."

    # Validation
    KEY_REQUIREMENTS = "Jira Project Key must be uppercase, start with a letter, and must be 2-10 chars in length."
    HTTPS_REQUIRED = "Site URL must use HTTPS for security."
    ATL_DOMAIN_REQUIRED = (
        "Site URL must be a valid Atlassian Cloud domain (e.g., company.atlassian.net)."
    )
    IMMUTABLE_SITE = "You cannot change the Site URL once a project is linked."
    IMMUTABLE_KEY = "You cannot change the Project Key after creation."
    DUPLICATE_PROJECT = "This project key already exists for this site URL."
    USER_NOT_FOUND = "User does not exist."
    ALREADY_MEMBER = "User is already a member."

    # General
    LEFT_PROJECT = "You have left the project."
    MEMBER_REMOVED = "Member removed successfully."
