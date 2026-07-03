"""
Capability-block framing and layer-boundary constraints for the
project-scoped git capability.

Fixes, as data, the framing of the git capability as one of three
independently configurable and independently failing capability members,
and the layer boundary that confines each externally-facing member's
reach so that neither the git member nor the github member ever touches
the server's internal command-to-driver-to-database chain.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import enum
from typing import FrozenSet


class CapabilityMember(enum.Enum):
    """One of three independently configurable, independently failing capability members.

    Each member can be configured, enabled, and can fail independently of
    the other two members; none of the three members implies or depends on
    the configuration or failure state of another.

    Attributes:
        GIT_BLOCK: The project-scoped git command block, operating on the
            filesystem working tree of a registered project via subprocess
            git.
        GITHUB_BLOCK: The GitHub command block, operating on the GitHub
            remote HTTP API.
        COMMIT_ON_WRITE_BEHAVIOUR: The commit-on-write behaviour attached
            to the existing project file write path.
    """

    GIT_BLOCK = "git_block"
    GITHUB_BLOCK = "github_block"
    COMMIT_ON_WRITE_BEHAVIOUR = "commit_on_write_behaviour"


CAPABILITY_MEMBERS: FrozenSet[CapabilityMember] = frozenset(CapabilityMember)

GIT_BLOCK_LAYER: str = "filesystem_subprocess_git"
GITHUB_BLOCK_LAYER: str = "github_http_api"
FORBIDDEN_TOUCH: str = "command_to_driver_to_database_chain"


class LayerBoundary:
    """The boundary confining the git block to the filesystem and the github block to the HTTP API.

    Neither the git block nor the github block touches the server's
    internal command-to-driver-to-database chain used by the server's own
    commands to reach their drivers and database.

    Attributes:
        git_block_layer: The layer the git capability member is confined
            to — the filesystem working tree of a registered project,
            accessed exclusively via subprocess git invocations.
        github_block_layer: The layer the github capability member is
            confined to — the GitHub HTTP API.
        forbidden_touch: The internal server layer neither the git block
            nor the github block may touch: the command-to-driver-to-database
            chain used by the server's own commands.
    """

    git_block_layer: str = GIT_BLOCK_LAYER
    github_block_layer: str = GITHUB_BLOCK_LAYER
    forbidden_touch: str = FORBIDDEN_TOUCH

    @staticmethod
    def is_touch_forbidden(layer_name: str) -> bool:
        """Report whether the named layer is the forbidden internal chain.

        Args:
            layer_name: The name of a layer to check.

        Returns:
            True if layer_name equals the forbidden internal
            command-to-driver-to-database chain layer, False otherwise.
        """
        return layer_name == FORBIDDEN_TOUCH
