import re
import json
import sys
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext

# Try to import required libraries
try:
    from dotenv import load_dotenv
    # Load .env from the same directory as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(script_dir, ".env"))
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("⚠️ 'python-dotenv' not found. Please install it: pip install python-dotenv")

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️ 'google-generativeai' library not found. AI features will be disabled. (pip install google-generativeai)")

class LabComponent:
    def __init__(self, name, category, attributes, documentation_text):
        self.name = name
        self.category = category
        self.attributes = attributes
        self.doc_text = documentation_text
        self.direct_dependencies = [] 
        self._parse_dependencies()

    def _parse_dependencies(self):
        patterns = [
            r"Requires:\s*\[(.*?)\]",
            r"Dependencies:\s*(.*?)(?:\.|$)",
            r"Must be connected to:\s*(.*?)(?:\.|$)"
        ]
        found_deps = set()
        for pattern in patterns:
            matches = re.findall(pattern, self.doc_text, re.IGNORECASE)
            for match in matches:
                items = [item.strip() for item in match.split(',')]
                for item in items:
                    if item:
                        found_deps.add(item)
        self.direct_dependencies = list(found_deps)

    def to_dict(self):
        """Serialize to dictionary for JSON saving."""
        return {
            "name": self.name,
            "category": self.category,
            "attributes": self.attributes,
            "doc_text": self.doc_text
        }

    @staticmethod
    def from_dict(data):
        """Deserialize from dictionary."""
        return LabComponent(
            data["name"], 
            data["category"], 
            data["attributes"], 
            data["doc_text"]
        )

    def to_prompt_string(self):
        return f"- Name: {self.name}\n  Specs: {json.dumps(self.attributes)}\n  Docs: {self.doc_text.strip()}"

class AISelector:
    def __init__(self):
        self.model = None
        self.api_key = None
        if GEMINI_AVAILABLE:
            self._configure_gemini()

    def _configure_gemini(self):
        # API Key is now loaded via load_dotenv() into os.environ
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # Folosim modelul Flash pentru viteză
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    def set_api_key(self, key):
        self.api_key = key
        if GEMINI_AVAILABLE and key:
            genai.configure(api_key=key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')

    def choose_best_component(self, requirement, candidates, user_intent):
        if not candidates: return None
        if len(candidates) == 1: return candidates[0]
        
        if not self.model:
            # Fallback if no API key
            return candidates[0]

        candidate_text = "\n".join([c.to_prompt_string() for c in candidates])
        
        # Enforced System Instruction for strict inventory use
        system_prompt = (
            "You are an expert Lab Automation Architect. "
            "Your sole function is to select the single best tool from the provided CANDIDATES list. "
            "DO NOT suggest, return, or mention any component not explicitly in the list. "
            "Output only valid JSON."
        )

        user_prompt = f"""
        I need to satisfy a dependency requirement using ONLY the tools listed in the 'AVAILABLE CANDIDATES' inventory below.

        REQUIREMENT: {requirement}
        USER DESIGN INTENT (Context): "{user_intent}"

        AVAILABLE CANDIDATES (Inventory):
        {candidate_text}

        INSTRUCTIONS:
        1. Compare candidate specs against the User Design Intent.
        2. Select the single best fit from the list above.
        3. Return ONLY a JSON object with this structure. The 'selected_component_name' MUST exactly match a name from the list:
        {{ "selected_component_name": "Exact Name From List", "reasoning": "Short explanation justifying the choice based on intent." }}
        """

        try:
            # Use Gemini's JSON response format feature
            response = self.model.generate_content(
                user_prompt,
                system_instruction=system_prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            
            content = response.text
            result_json = json.loads(content)
            selected_name = result_json.get("selected_component_name")
            
            # Match the AI's string selection back to a real object
            for comp in candidates:
                if comp.name.lower() == selected_name.lower():
                    return comp
            
            # Fallback if AI hallucinated a name not in the list
            print(f"⚠️ AI selected unknown name '{selected_name}'. Defaulting to first option.")
            return candidates[0]

        except Exception as e:
            print(f"❌ AI Error: {e}. Defaulting to first option.")
            return candidates[0]

class DependencyGraph:
    def __init__(self):
        self.registry = {}
        self.ai_agent = AISelector()

    def ingest_documentation(self, name, category, attributes, doc_text):
        component = LabComponent(name, category, attributes, doc_text)
        self.registry[name.lower()] = component
        return component

    def get_candidates(self, requirement):
        req_lower = requirement.lower()
        # 1. Check for exact match
        if req_lower in self.registry:
            return [self.registry[req_lower]]
        
        # 2. Check for category match
        candidates = []
        for comp in self.registry.values():
            if comp.category.lower() == req_lower:
                candidates.append(comp)
        return candidates

    def build_lab_config(self, root_request, user_intent):
        if not self.registry:
            return None, [], "Database is empty! Please load lab_inventory.json."
        
        # --- Aggressively clean and normalize the user input ---
        normalized_request = root_request.strip().lower()
        
        print("--------------------------------------------------")
        print(f"[DEBUG] Raw User Request: '{root_request}'")
        print(f"[DEBUG] Normalized Search Key: '{normalized_request}'")
        print("--------------------------------------------------")

        # Find initial candidates for the root system
        root_candidates = []
        
        # 1. Check for exact match first (most likely success)
        if normalized_request in self.registry:
            root_candidates.append(self.registry[normalized_request])
        else:
            # 2. Substring match for flexibility
            for key, comp in self.registry.items():
                if normalized_request in key: 
                    root_candidates.append(comp)
        
        if not root_candidates:
            # Fallback if the normalized key couldn't find anything
            return None, [], f"Root item '{root_request}' not found in inventory."

        # AI Selects the root node
        root_node = self.ai_agent.choose_best_component(root_request, root_candidates, user_intent)
        
        build_plan = {} 
        missing_items = []
        stack = [root_node]
        visited = set()
        resolved_map = {} 

        while stack:
            current_comp = stack.pop()
            if current_comp.name in visited: continue
            visited.add(current_comp.name)

            if current_comp.name not in build_plan:
                build_plan[current_comp.name] = []

            for dep_req in current_comp.direct_dependencies:
                # Check if we already resolved this requirement type for consistency
                if dep_req in resolved_map:
                    chosen_comp = resolved_map[dep_req]
                else:
                    # Find candidates in inventory for this requirement
                    candidates = self.get_candidates(dep_req)
                    
                    if not candidates:
                        missing_items.append(dep_req)
                        continue
                    
                    chosen_comp = self.ai_agent.choose_best_component(dep_req, candidates, user_intent)
                    resolved_map[dep_req] = chosen_comp

                build_plan[current_comp.name].append(chosen_comp.name)
                stack.append(chosen_comp)

        return build_plan, missing_items, root_node.name

    def save_to_json(self, filename="lab_inventory.json"):
        data = [comp.to_dict() for comp in self.registry.values()]
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Save error: {e}")
            return False

    def load_from_json(self, filename):
        if not os.path.exists(filename): return False
        try:
            if os.path.getsize(filename) == 0:
                print("⚠️ JSON file is empty.")
                return False
                
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list) or not data:
                print("⚠️ JSON file is loaded, but content is not a list or is empty.")
                return False
                
            self.registry = {}
            for item in data:
                comp = LabComponent.from_dict(item)
                self.registry[comp.name.lower()] = comp
            return True
        except json.JSONDecodeError:
            print("❌ JSON Decode Error: File content is not valid JSON.")
            return False
        except Exception as e:
            print(f"❌ Load error: {e}")
            return False

class LabApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🧬 Lab Architect & Inventory Manager (Gemini Powered)")
        self.geometry("1100x700")
        self.graph = DependencyGraph()
        
        # Styles
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Treeview", font=('Segoe UI', 10), rowheight=25)
        self.style.configure("TButton", font=('Segoe UI', 10))

        self._init_ui()
        self._initialize_data()

    def _init_ui(self):
        # --- Top Toolbar ---
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        
        ttk.Button(toolbar, text="💾 Save Database", command=self.save_db).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="📂 Load Database", command=self.load_db_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="➕ Add/Download Tool", command=self.open_add_tool_window).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="🏗️ Build Project (Gemini)", command=self.open_build_window).pack(side=tk.LEFT, padx=2)
        
        # API Key Indicator
        self.api_status_var = tk.StringVar(value="API Key: Check .env")
        ttk.Label(toolbar, textvariable=self.api_status_var).pack(side=tk.RIGHT, padx=10)

        # --- Main Content ---
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left Panel: Inventory Tree
        frame_tree = ttk.LabelFrame(paned, text="Inventory Knowledge Graph", padding=5)
        paned.add(frame_tree, weight=1)

        self.tree = ttk.Treeview(frame_tree, columns=("Category", "Dependencies"), show="tree headings")
        self.tree.heading("#0", text="Component / System")
        self.tree.heading("Category", text="Category")
        self.tree.heading("Dependencies", text="Direct Requirements")
        self.tree.column("#0", width=300)
        self.tree.column("Category", width=150)
        
        # Bind Selection Event to visualize tree
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        vsb = ttk.Scrollbar(frame_tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Right Panel: Details & Logs
        frame_detail = ttk.LabelFrame(paned, text="System Logs & Tree Visualization", padding=5)
        paned.add(frame_detail, weight=1)
        
        self.log_area = scrolledtext.ScrolledText(frame_detail, font=('Consolas', 9), state='disabled')
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _initialize_data(self):
        """
        Automatically loads 'lab_inventory.json' from the script's directory.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        default_file = os.path.join(script_dir, "lab_inventory.json")
        
        self.log("--- Initializing ---")
        if os.path.exists(default_file):
            self.log(f"📂 Attempting to load database from: {default_file}")
            
            # Use the robust load_from_json method
            if self.graph.load_from_json(default_file):
                self.log(f"✅ Database loaded successfully! {len(self.graph.registry)} items found.")
                # Print the key we need to search for the default item
                if "advanced liquid handler system" in self.graph.registry:
                    print("[INFO] The key 'advanced liquid handler system' IS present in registry.")
                else:
                    print("[INFO] The key 'advanced liquid handler system' IS NOT present.")
                    
            else:
                self.log("❌ Database failed to load. Check console for error details.")
        else:
            self.log(f"ℹ️ File 'lab_inventory.json' not found. Starting empty.")
        
        self.refresh_tree_view()
        
        # Check API Key
        if self.graph.ai_agent.api_key:
             self.api_status_var.set("✅ Gemini Key Loaded")
        else:
             self.api_status_var.set("⚠️ No Gemini Key (.env)")

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, f"> {message}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def refresh_tree_view(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        categories = {}
        for comp in self.graph.registry.values():
            cat = comp.category
            if cat not in categories: categories[cat] = []
            categories[cat].append(comp)

        for cat in sorted(categories.keys()):
            cat_node = self.tree.insert("", tk.END, text=cat, open=False)
            for comp in categories[cat]:
                deps = ", ".join(comp.direct_dependencies) if comp.direct_dependencies else "None"
                self.tree.insert(cat_node, tk.END, text=comp.name, values=(comp.category, deps))
        
        self.log(f"Tree View Refreshed. Items: {len(self.graph.registry)}")

    # --- Tree Visualization Logic ---
    def on_tree_select(self, event):
        selected_items = self.tree.selection()
        if not selected_items: return
        item_id = selected_items[0]
        item_text = self.tree.item(item_id, "text")
        
        if item_text.lower() in self.graph.registry:
            comp = self.graph.registry[item_text.lower()]
            self.display_component_tree(comp)

    def display_component_tree(self, root_comp):
        self.log_area.config(state='normal')
        self.log_area.delete("1.0", tk.END)
        
        self.log_area.insert(tk.END, f"📦 SELECTED: {root_comp.name}\n")
        self.log_area.insert(tk.END, f"   Category: {root_comp.category}\n")
        if root_comp.attributes:
             self.log_area.insert(tk.END, f"   Specs: {root_comp.attributes}\n")
        self.log_area.insert(tk.END, "="*50 + "\n\n")
        self.log_area.insert(tk.END, "🌳 FULL DEPENDENCY HIERARCHY:\n")
        
        self._print_recursive_tree(root_comp)
        
        self.log_area.config(state='disabled')

    def _print_recursive_tree(self, comp, prefix="", is_last=True, visited=None):
        if visited is None: visited = set()
        
        if comp.name in visited:
            self.log_area.insert(tk.END, f"{prefix}{'└── ' if is_last else '├── '}{comp.name} (Cycle Detected 🔄)\n")
            return
        
        connector = "└── " if is_last else "├── "
        self.log_area.insert(tk.END, f"{prefix}{connector}{comp.name}\n")
        
        visited.add(comp.name)
        
        new_prefix = prefix + ("    " if is_last else "│   ")
        reqs = comp.direct_dependencies
        
        for i, req in enumerate(reqs):
            is_last_child = (i == len(reqs) - 1)
            candidates = self.graph.get_candidates(req)
            
            if not candidates:
                self.log_area.insert(tk.END, f"{new_prefix}{'└── ' if is_last_child else '├── '}⚠️ {req} (Missing)\n")
            elif len(candidates) == 1:
                self._print_recursive_tree(candidates[0], new_prefix, is_last_child, visited.copy())
            else:
                self.log_area.insert(tk.END, f"{new_prefix}{'└── ' if is_last_child else '├── '}❓ {req} (Abstract: {len(candidates)} options)\n")
                option_prefix = new_prefix + ("    " if is_last_child else "│   ")
                for j, cand in enumerate(candidates):
                    is_last_opt = (j == len(candidates) - 1)
                    self._print_recursive_tree(cand, option_prefix, is_last_opt, visited.copy())

    def save_db(self):
        if self.graph.save_to_json("lab_inventory.json"):
            messagebox.showinfo("Success", "Database saved to 'lab_inventory.json'")
            self.log("💾 Database saved.")
        else:
            messagebox.showerror("Error", "Failed to save database.")

    def load_db_dialog(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        default_file = os.path.join(script_dir, "lab_inventory.json")
        
        if self.graph.load_from_json(default_file):
            self.refresh_tree_view()
            messagebox.showinfo("Success", "Database loaded!")
            self.log(f"📂 Database loaded successfully! {len(self.graph.registry)} items found.")
        else:
            messagebox.showerror("Error", "File 'lab_inventory.json' not found or failed to load. Check console logs.")

    # --- Add Tool Window ---
    def open_add_tool_window(self):
        win = tk.Toplevel(self)
        win.title("Download / Add Tool")
        win.geometry("500x600")

        ttk.Label(win, text="Name:").pack(anchor=tk.W, padx=10, pady=(10,0))
        entry_name = ttk.Entry(win)
        entry_name.pack(fill=tk.X, padx=10)

        ttk.Label(win, text="Category:").pack(anchor=tk.W, padx=10, pady=(10,0))
        entry_cat = ttk.Entry(win)
        entry_cat.pack(fill=tk.X, padx=10)

        ttk.Label(win, text="Documentation Source (URL Simulation):").pack(anchor=tk.W, padx=10, pady=(10,0))
        entry_url = ttk.Entry(win)
        entry_url.insert(0, "https://manufacturer.com/specs/product-123")
        entry_url.pack(fill=tk.X, padx=10)

        ttk.Label(win, text="Paste Documentation Text (Specs & Requirements):").pack(anchor=tk.W, padx=10, pady=(10,0))
        text_docs = tk.Text(win, height=15)
        text_docs.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        text_docs.insert(tk.END, "Description: High speed unit.\nRequires: [Power Supply, Cooling Unit]\n")

        def submit():
            name = entry_name.get().strip()
            cat = entry_cat.get().strip()
            docs = text_docs.get("1.0", tk.END).strip()
            if not name:
                messagebox.showerror("Error", "Name required")
                return
            self.graph.ingest_documentation(name, cat, {}, docs)
            self.refresh_tree_view()
            self.log(f"➕ Added tool: {name}")
            win.destroy()

        ttk.Button(win, text="Simulate Download & Add to Graph", command=submit).pack(pady=10)

    def open_build_window(self):
        win = tk.Toplevel(self)
        win.title("Gemini Lab Architect")
        win.geometry("600x700")

        ttk.Label(win, text="System to Build:").pack(anchor=tk.W, padx=10, pady=(10,0))
        entry_target = ttk.Entry(win)
        entry_target.pack(fill=tk.X, padx=10)
        # S-A SCHIMBAT ÎN Advanced Liquid Handler System PENTRU A CORESPUNDE CU JSON-UL TĂU
        entry_target.insert(0, "Advanced Liquid Handler System") 

        ttk.Label(win, text="Design Intent / Requirements:").pack(anchor=tk.W, padx=10, pady=(10,0))
        text_intent = tk.Text(win, height=4, font=('Segoe UI', 10))
        text_intent.pack(fill=tk.X, padx=10)
        text_intent.insert("1.0", "I need a high-throughput system for massive parallel screening. It must operate on standard 24V logic and use durable ceramic components for the piston arrays to minimize maintenance.")

        self.lbl_status = ttk.Label(win, text="Ready", font=('Segoe UI', 10, 'italic'), foreground="gray")
        self.lbl_status.pack(pady=5)

        result_area = scrolledtext.ScrolledText(win, height=20)
        result_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.is_building = False
        
        def animate_loading():
            chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            idx = 0
            def step():
                if not self.is_building or not win.winfo_exists(): return
                nonlocal idx
                self.lbl_status.config(text=f"Gemini is thinking {chars[idx]}", foreground="blue")
                idx = (idx + 1) % len(chars)
                win.after(100, step)
            step()

        def run_build():
            target = entry_target.get().strip()
            intent = text_intent.get("1.0", tk.END).strip()
            if not target: return

            self.is_building = True
            result_area.delete("1.0", tk.END)
            animate_loading()
            
            btn_generate.config(state='disabled')

            def task():
                try:
                    plan, missing, root_name = self.graph.build_lab_config(target, intent)
                except Exception as e:
                    plan, missing, root_name = None, [], str(e)

                self.is_building = False
                
                def update_ui():
                    if not win.winfo_exists(): return
                    self.lbl_status.config(text="Done.", foreground="green")
                    btn_generate.config(state='normal')
                    
                    if not plan:
                        result_area.insert(tk.END, f"❌ Failed: {root_name}\n")
                    else:
                        result_area.insert(tk.END, f"✅ Build Plan for: {root_name}\n")
                        result_area.insert(tk.END, "="*40 + "\n")
                        
                        def print_recursive(node, prefix="", is_last=True):
                            connector = "└── " if is_last else "├── "
                            line = prefix + connector + node + "\n"
                            result_area.insert(tk.END, line)
                            prefix += "    " if is_last else "│   "
                            children = plan.get(node, [])
                            count = len(children)
                            for i, child in enumerate(children):
                                print_recursive(child, prefix, i == count - 1)

                        print_recursive(root_name)
                        
                        if missing:
                            result_area.insert(tk.END, "\n⚠️ Missing Components:\n")
                            for m in missing:
                                result_area.insert(tk.END, f" - {m}\n")

                win.after(0, update_ui)

            threading.Thread(target=task).start()

        btn_generate = ttk.Button(win, text="Generate Configuration", command=run_build)
        btn_generate.pack(pady=5)

def main():
    app = LabApp()
    app.mainloop()

if __name__ == "__main__":
    main()