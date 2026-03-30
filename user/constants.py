class UserMessages:
    # Success Messages
    REGISTRATION_SUCCESS = "User registered successfully."
    LOGIN_SUCCESS = "Login successful."
    LOGOUT_SUCCESS = "Successfully logged out."
    SIGNUP_LINK_SENT = "Verification link has been sent to your email."

    # Error Messages - Auth & Tokens
    TOKEN_REQUIRED = "Token is required for registration."
    TOKEN_INVALID = "The provided token is invalid or missing the email claim."
    REFRESH_TOKEN_MISSING = "Refresh token missing."
    INVALID_BASE64_PASSWORD = "Invalid base64 encoded password."

    # Error Messages - User Logic
    USER_ALREADY_EXISTS = "An account with this email already exists."
    EMAIL_MODIFICATION_FORBIDDEN = "This field cannot be modified."
    JIRA_ID_MODIFICATION_FORBIDDEN = "This field cannot be modified."
    SIGNUP_REQUEST_FAILED = "Signup request failed"
    EMAIL_SEND_FAILURE = "Failed to send email: Some error occurred"
