def serialize_profile(user):
    return {
        "userId": user.id,
        "displayName": user.display_name,
        "avatarUrl": user.avatar_url,
    }

