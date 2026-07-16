"""Step 5 — 2D analysis: run a polar sweep and work with the numbers.

`project.analysis_2d(...)` holds your sweep parameters; `run()` returns
raw arrays (one value per computed point, unconverged points are None),
`figures()` returns the web app's ready-made Plotly figures instead.

    python 05_polar_analysis.py
"""

from pytakeoff import TakeoffClient

API_KEY = "tk_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # get a key in the GUI (Account -> API Keys) or run: python -m pytakeoff

with TakeoffClient(api_key=API_KEY) as client:
    # Use the project open in your session, or your most recent one if none is
    # open (so this runs even without the web app):
    project = client.projects.current() or client.projects.open(client.projects.list()[0]["name"])
    print(f"Project: {project.name}")

    analysis = project.analysis_2d(
        alpha_range=[-5, 0, 5, 10],
        reynolds_million=1.0,
        flap_lock=True,     # plain alpha sweep (no flap sweep)
        solver=["NN"],
        fluid="water",
    )
    print("Parameters:", analysis.parameters())

    result = analysis.run()
    print(f"\nVariables per point: {result['variables'][:9]} ...")
    for s in result["sections"]:
        d = s["data"]
        rows = [
            (a, cl, cd, g)
            for a, cl, cd, g in zip(d["alpha"], d["Cl"], d["Cd"], d["Cl_Cd"])
            if cl is not None
        ]
        best = max(rows, key=lambda r: r[3])
        print(f"  {s['section']}: {s['n_points']} points | "
              f"best glide Cl/Cd={best[3]:.1f} at alpha={best[0]:.0f} "
              f"(Cl={best[1]:.3f}, Cd={best[2]:.5f})")

    # Chordwise pressure distribution of the last sweep point:
    d = result["sections"][0]["data"]
    if d.get("top_Cp") and d["top_Cp"][-1]:
        print(f"\nCp distribution at alpha={d['alpha'][-1]:.0f}: "
              f"{len(d['top_Cp'][-1])} points, min Cp={min(d['top_Cp'][-1]):.2f}")

    # The web app's ready-made Plotly figures are one call away:
    #   figures = analysis.figures()
