"""Mine layout priors and write datasets/metadata/cleaning/layout_priors.json."""

# Entry point for the miner.
from spacedesigner.data.layout_priors import run

# Run only when executed as a script.
if __name__ == "__main__":
    # Mine everything.
    priors = run()
    # One-line summary per source.
    print("sun objects kept:", priors["sun_rgbd"]["objects_kept"])
    # Room drops.
    print("sun room drops:", priors["sun_rgbd"]["room_drops"])
    # Rooms per type.
    print("sun rooms:", priors["sun_rgbd"]["rooms_kept_by_type"])
    # Published size priors.
    print("size priors:", len(priors["sun_rgbd"]["object_size"]))
    # Published wall priors.
    print("wall priors:", len(priors["sun_rgbd"]["wall_distance"]))
    # Omissions.
    print(
        "omitted:",
        [o["prior"] for s in priors.values() if isinstance(s, dict) for o in s.get("omitted", [])],
    )
