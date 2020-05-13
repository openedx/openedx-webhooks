"""
Utilities for working with GitHub.
"""

from .decorators import inject_gh


@inject_gh
def get_repos_with_webhook(
        gh, payload_url, repo_type='public', exclude_inactive=False
):
    """
    Find repos that contain webhooks with the specified payload_url.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session
        payload_url (str): The webhook payload URL, this acts as the key
            of the webhooks
        repo_type (str): 'all', 'owner', 'public', 'private', 'member'
        exclude_inactive (bool): Exclude inactive webhooks from the result

    Returns:
        Iterator[github3.repos.repo.Repository]
    """
    for repo in gh.iter_repos(type=repo_type):
        if repo_contains_webhook(repo, payload_url, exclude_inactive):
            yield repo


@inject_gh
def create_or_update_webhook(
        gh, repo_name, config, events, active=True, dry_run=False
):
    """
    Update or create webhook in repo.

    Arguments:
        gh (github3.GitHub): An authenticated GitHub API client session
        repo_name (str)
        config (Dict[str, str]): key-value pairs which act as settings
            for this hook
        events (List[str]): events the hook is triggered for
        active (bool): whether the hook is actually triggered
        dry_run (bool): Don't really create the hook

    Returns:
        Tuple[
            github3.repos.hook.Hook,
            bool,
            List[github3.repos.hook.Hook]
        ]: Returns (
            the created or updated hook,
            ``True`` if created, ``False`` if edited,
            a list of hooks deleted (if any)
        )
    """
    repo = get_repo(gh, repo_name)
    return create_or_update_webhooks_for_repo(
        repo, config, events, active, dry_run
    )


@inject_gh
def get_repo(gh, repo_name):
    return gh.repository(*repo_name.split('/'))


def create_or_update_webhooks_for_repo(
        repo, config, events, active=True, dry_run=False
):
    """
    Update or create webhook in repo.

    Arguments:
        repo (github3.repos.repo.Repository)
        config (Dict[str, str]): key-value pairs which act as settings
            for this hook
        events (List[str]): events the hook is triggered for
        active (bool): whether the hook is actually triggered
        dry_run (bool): Don't really create the hook

    Returns:
        Tuple[
            github3.repos.hook.Hook,
            bool,
            List[github3.repos.hook.Hook]
        ]: Returns (
            the created or updated hook,
            ``True`` if created, ``False`` if edited,
            a list of hooks deleted (if any)
        )
    """
    payload_url = config['url']

    existing_hooks = list(get_webhooks(repo, payload_url))

    if existing_hooks:
        hook_to_edit = _get_most_recent_hook(existing_hooks)
        hooks_to_delete = list(existing_hooks)
        hooks_to_delete.remove(hook_to_edit)

        hook = edit_hook(repo, hook_to_edit, config, events, active, dry_run)
        delete_hooks(repo, hooks_to_delete, dry_run)
        created = False
    else:
        hooks_to_delete = []
        hook = create_hook(repo, config, events, active, dry_run)
        created = True

    return hook, created, hooks_to_delete


def create_hook(repo, config, events, active, dry_run=False):
    """
    Create a webhook in the specified repo.

    Arguments:
        repo (github3.repos.repo.Repository)
        config (Dict[str, str]): key-value pairs which act as settings
            for this hook
        events (List[str]): events the hook is triggered for
        active (bool): whether the hook is actually triggered
        dry_run (bool): Don't really create the hook

    Returns:
        (github3.repos.hook.Hook)

    Raises:
        Exception: If the hook can't be created for some reason
    """
    if dry_run:
        return None
    hook = repo.create_hook('web', config, events, active)
    if not hook:
        raise Exception("Can't create {} webhook: {}".format(
            repo_name(repo), config['url']
        ))
    return hook


def edit_hook(repo, hook, config, events, active, dry_run=False):
    """
    Edit a webhook in the specified repo.

    Arguments:
        repo (github3.repos.repo.Repository)
        hook (github3.repos.hook.Hook)
        config (Dict[str, str]): key-value pairs which act as settings
            for this hook
        events (List[str]): events the hook is triggered for
        active (bool): whether the hook is actually triggered
        dry_run (bool): Don't really edit the hook

    Returns:
        github3.repos.hook.Hook: The updated hook object

    Raises:
        Exception: If the hook can't be edited for some reason
    """
    if dry_run:
        return hook
    result = hook.edit(config, events, active=active)
    if not result:
        raise Exception("Can't edit {} webhook({}): {}".format(
            repo_name(repo), hook.id, hook.config['url']
        ))
    updated_hook = repo.hook(hook.id)
    return updated_hook


def delete_hook(repo, hook, dry_run=False):
    """
    Delete a webhook in the specified repo.

    Arguments:
        repo (github3.repos.repo.Repository)
        hook (github3.repos.hook.Hook)
        dry_run (bool): Don't really delete the hook

    Raises:
        Exception: If the hook can't be deleted for some reason
    """
    if dry_run:
        return
    result = hook.delete()
    if not result:
        raise Exception("Can't delete {} webhook({}): {}".format(
            repo_name(repo), hook.id, hook.config['url']
        ))


def delete_hooks(repo, hooks, dry_run=False):
    """
    Delete webhooks in the specified repo.

    Arguments:
        repo (github3.repos.repo.Repository)
        hooks (List[github3.repos.hook.Hook])
        dry_run (bool): Don't really delete the hook
    """
    if not dry_run:
        for hook in hooks:
            delete_hook(repo, hook, dry_run)


def get_webhooks(repo, payload_url):
    """
    Get webhooks installed in a given repo that match the payload_url.

    Arguments:
        repo (github3.repos.repo.Repository)
        payload_url (str): The webhook payload URL, this acts as the key
            of the webhooks

    Returns:
        Iterator[github3.repos.hook.Hook]
    """
    hooks = (
        h for h in repo.iter_hooks()
        if h.name == 'web' and h.config['url'] == payload_url
    )
    return hooks


def repo_contains_webhook(repo, payload_url, exclude_inactive=False):
    """
    Determine whether a repo contains webhooks with the specified payload_url.

    Arguments:
        repo (github3.repos.repo.Repository)
        payload_url (str): The webhook payload URL, this acts as the key
            of the webhooks
        exclude_inactive (bool): Exclude inactive webhooks from the result

    Returns:
        bool
    """
    hooks = get_webhooks(repo, payload_url)
    is_active_list = [h.active for h in hooks]
    is_active = any(is_active_list)
    if is_active_list and (is_active or not exclude_inactive):
        return True
    return False


def repo_name(repo):
    """
    Construct the repo name.

    Arguments:
        repo (github3.repos.repo.Repository)

    Returns:
        str
    """
    return "{0.owner.login}/{0.name}".format(repo)


def _get_most_recent_hook(hooks):
    """
    Return the most recent hook.

    Most recent is defined by active status, then updated datetime.
    This means active hooks will be prioritized over inactive ones,
    no matter what the updated datetimes are.

    Arguments:
        hooks (Iterable[github3.repos.hook.Hook])

    Returns:
        Optional(github3.repos.hook.Hook)
    """
    try:
        return max(hooks, key=lambda h: (h.active, h.updated_at))
    except ValueError:
        return None
