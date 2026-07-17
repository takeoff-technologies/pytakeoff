"""Step 6 — 2D optimization: configure an OptiAeroFoil, run it, inspect the result.

Objectives use SailFish's vocabulary: `func` is "minCd", "maxCl",
"maxGlide" (or any min<var>/max<var>), evaluated at the given `Re`,
`alpha`, `flap_angle`... `solve_for` picks what floats: "fixed",
"alpha" (to hit `target_Cl`), or "flap". Constraints use the same
fields as the GUI tables.

This demo runs a deliberately small optimization (maxiter=10) and
deletes its entity at the end so it stays repeatable.

    python 06_optimization.py
"""

from pytakeoff import TakeoffClient

# Ran `python -m pytakeoff`? Leave this line exactly as it is: the all-x
# placeholder counts as no key, so your saved credentials (or the
# TAKEOFF_API_KEY env var) are used automatically.
# Otherwise, paste your own key here - GUI: Account -> API Keys.
API_KEY = "tk_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

with TakeoffClient(api_key=API_KEY) as client:
    # Use the project open in your session, or your most recent one if none is
    # open (so this runs even without the web app):
    project = client.projects.current() or client.projects.open(client.projects.list()[0]["name"])
    sections = project.foil_sections()

    # ---- configure ----------------------------------------------------
    opt = project.create_optimization_2d(
        "example_opt",
        initial_section=sections[0].name,
        solver="NN",
        optimizer_config={"maxiter": 10, "tol": 1e-3},
    )
    opt.set_objectives([
        {"func": "maxGlide", "Re": 1e6, "alpha": 4.0, "solve_for": "fixed"},
    ])
    opt.set_constraints(
        geo=[{"variable": "get_tc", "operator": ">", "value": 0.10}],
        aero=[{"variable": "Cl", "operator": ">", "value": 0.8,
               "Re": 1e6, "alpha": 8.0, "solve_for": "fixed"}],
    )
    print(f"Configured {opt.name} on '{sections[0].name}'")

    # ---- run ------------------------------------------------------------
    response = opt.run(
        on_progress=lambda pct, msg: print(f"  {float(pct):5.1f}%  {msg or ''}"),
        timeout=None,
    )
    print("Success:", response.get("success"))

    # ---- inspect ----------------------------------------------------------
    r = opt.result()  # latest run
    data = r["opt_data"]
    print(f"\nRun {r['run_number']}: {data['total_iterations']} iterations")
    print(f"  objective score: {data['score']:.6f}")
    obj = data.get("objective_1", {})
    print(f"  at design point: Cl={obj.get('Cl'):.4f}  Cd={obj.get('Cd'):.6f}  "
          f"glide={obj.get('Cl') / obj.get('Cd'):.1f}")

    # Keep it? save the optimized section into the project:
    #   saved = opt.save_result()
    #   print("Saved as:", saved["section_name"])

    # ---- clean up so the demo is repeatable ------------------------------
    project.delete_entity("OptiAeroFoil", id=opt.id)
    print(f"\nDeleted {opt.name} (demo cleanup; nothing was saved).")
