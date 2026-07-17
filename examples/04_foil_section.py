"""Step 4 — foil sections: control points, geometric & structural parameters.

Three get/set pairs on the project currently open in your session:

    section.control_points() / section.set_control_points(upper=, lower=)
    section.geometry()       / section.set_geometry(tc=, camber=, ...)
    section.structure()      / section.set_structure(area=, Ixx=, ...)

Values use the same units as the GUI (tc / camber / TE thickness in
percent of chord). Setting a parameter refits the B-spline, so the
achieved value can differ marginally from the requested one.

This script makes the first section 5% thicker, then restores the
original control points exactly. Nothing is saved to disk.

    python 04_foil_section.py
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
    print(f"Project: {project.name}")

    sections = project.foil_sections()
    print(f"{len(sections)} foil section(s): {[s.name for s in sections]}")
    section = sections[0]

    # ---- get: control points, geometric params, structural params ------
    cp = section.control_points()
    print(f"\n{section.name}: {cp['n_coefs']} control points per side, "
          f"degree {cp['degree']:.0f}")
    print(f"  first upper points: {cp['upper'][:3]}")

    geo = section.geometry()
    print(f"  geometry:  tc={geo['tc']:.3f}%  camber={geo['camber']:.3f}%  "
          f"LE radius={geo['le_radius']:.4f}  TE thickness={geo['te_thickness']:.3f}%")

    struct = section.structure()
    print(f"  structure: area={struct['area']:.5f}  Ixx={struct['Ixx']:.3e}  "
          f"SMx={struct['SMx']:.3e}  J={struct['J']:.3e}")

    # ---- set: make it 5% thicker (parametric refit) ---------------------
    target = geo["tc"] * 1.05
    after = section.set_geometry(tc=target)
    print(f"\nset_geometry(tc={target:.3f}) -> achieved tc={after['tc']:.3f}%")
    print(f"  area is now {section.structure()['area']:.5f} (thicker section)")

    # ---- restore the exact original shape -------------------------------
    section.set_control_points(upper=cp["upper"], lower=cp["lower"])
    print(f"\nRestored original control points; tc back to "
          f"{section.geometry()['tc']:.3f}%")
    print("(Nothing was saved — the draft matches the original geometry again.)")
