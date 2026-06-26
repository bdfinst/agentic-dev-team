# FAIL: tracker IDs bleed into Python `#` comments.
# Cross-language proof that the comment-hygiene rule is not TS-specific.


class NestingConfig:
    def __init__(self):
        # Opt-in NFP-based placement (epic #24, P3-P5): slower but denser.
        self.use_nfp_placement = False

        # Remnant-aware fitness weights (#41): mild pull toward a clustered pack.
        self.gravity_weight = 0.0

        # See JIRA-1187 for the rationale behind this default.
        self.kerf = 1
