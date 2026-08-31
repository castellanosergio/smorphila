landmark_names = [
    "SNOUT",
    "VENT",
    "LHead1",
    "LHead2",
    "LHead3",
    "RHead1",
    "RHead2",
    "RHead3",
    "LArmPit",
    "LElb",
    "LMCarp",
    "LFingerHand1",
    "LFingerHand2",
    "LFingerHand3",
    "LFingerHand4",
    "RArmPit",
    "RElb",
    "RMCarp",
    "RFingerHand1",
    "RFingerHand2",
    "RFingerHand3",
    "RFingerHand4",
    "LKnee",
    "LTar",
    "LToe",
    "RKnee",
    "RTar",
    "RToe",
]

landmarks_groups = {
    "SVL": {"landmarks": ["SNOUT", "VENT"], "angles": []},
    "HEAD": {
        "landmarks": [
            "SNOUT",
            "LHead1",
            "LHead2",
            "LHead3",
            "LArmPit",
            "RArmPit",
            "RHead3",
            "RHead2",
            "RHead1",
            "SNOUT",
        ],
        "angles": [],
    },
    "L_FORELIMB": {
        "landmarks": ["LArmPit", "LElb", "LMCarp"],
        "angles": [180, 90, 0],
    },
    "R_FORELIMB": {
        "landmarks": ["RArmPit", "RElb", "RMCarp"],
        "angles": [0, -90, 0],
    },
    "L_HINDLIMB": {
        "landmarks": ["VENT", "LKnee", "LTar", "LToe"],
        "angles": [180, -90, 90, 90],
    },
    "R_HINDLIMB": {
        "landmarks": ["VENT", "RKnee", "RTar", "RToe"],
        "angles": [0, 90, -90, -90],
    },
    "L_HAND1": {
       "landmarks": ["LMCarp", "LFingerHand1"],
       "angles": [-90,-90]
    },
    "L_HAND2": {
       "landmarks": ["LMCarp", "LFingerHand2"],
       "angles": [-60, -60]
    },
    "L_HAND3": {
       "landmarks": ["LMCarp", "LFingerHand3"],
       "angles": [-30, -30]
    },
    "L_HAND4": {
       "landmarks": ["LMCarp", "LFingerHand4"],
       "angles": [0, 0]
    },
    "R_HAND1": {
       "landmarks": ["RMCarp", "RFingerHand1"],
       "angles": [270, 90]
    },
    "R_HAND2": {
       "landmarks": ["RMCarp", "RFingerHand2"],
       "angles": [240, 60]
    },
    "R_HAND3": {
       "landmarks": ["RMCarp", "RFingerHand3"],
       "angles": [210, 30]
    },
    "R_HAND4": {
       "landmarks": ["RMCarp", "RFingerHand4"],
       "angles": [180, 0]
    }
}

semilandmarks = {
    "MUSO_Sx": {
        "landmarks": ["LHead3", "SNOUT"],
        "nsemilandmarks": [8],
        "coordinates": [],
    },
    "MUSO_Dx": {
        "landmarks": ["RHead3", "SNOUT"],
        "nsemilandmarks": [8],
        "coordinates": [],
    },
}
