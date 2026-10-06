import {
  apiRequest,
  getCurrentUser,
} from "./api.js";

import "../styles/navigation.css";


export async function initializeNavigation() {
  const sidebar = document.querySelector(".sidebar");

  if (!sidebar) {
    return;
  }

  const toggle = document.createElement("button");

  toggle.type = "button";
  toggle.id = "hsm-sidebar-toggle";
  toggle.textContent = "☰";
  toggle.setAttribute("aria-label", "Toggle sidebar");

  if (!sidebar.id) {
    sidebar.id = "hsm-sidebar";
  }

  toggle.setAttribute("aria-controls", sidebar.id);

  document.body.append(toggle);


  function setSidebarClosed(closed) {
    document.documentElement.classList.toggle(
      "hsm-sidebar-closed",
      closed,
    );

    toggle.setAttribute("aria-expanded", String(!closed));

    try {
      sessionStorage.setItem(
        "hsm:sidebar-closed",
        closed ? "yes" : "no",
      );
    } catch {
      // Sidebar still works without browser storage.
    }
  }


  let previouslyClosed = false;

  try {
    previouslyClosed =
      sessionStorage.getItem("hsm:sidebar-closed") === "yes";
  } catch {
    // Default opened.
  }

  setSidebarClosed(previouslyClosed);

  toggle.addEventListener("click", () => {
    setSidebarClosed(
      !document.documentElement.classList.contains(
        "hsm-sidebar-closed",
      ),
    );
  });


  try {
    const response = await getCurrentUser();

    const csrfToken = response.csrf_token;

    if (!csrfToken) {
      throw new Error("CSRF token is unavailable.");
    }

    const footer = document.createElement("div");
    footer.className = "hsm-sidebar-footer";

    const logout = document.createElement("button");
    logout.type = "button";
    logout.id = "hsm-logout";
    logout.textContent = "Log out";

    footer.append(logout);
    sidebar.append(footer);

    logout.addEventListener("click", async () => {
      logout.disabled = true;

      try {
        await apiRequest("/auth/logout", {
          method: "POST",
          headers: {
            "X-CSRF-Token": csrfToken,
          },
        });

        window.location.replace("/login");
      } catch (error) {
        if (error?.status === 401) {
          window.location.replace("/login");
          return;
        }

        alert(error?.message || "Unable to log out.");
        logout.disabled = false;
      }
    });
  } catch (error) {
    if (error?.status === 401) {
      window.location.replace("/login");
    } else {
      console.error("Navigation initialization failed:", error);
    }
  }
}
