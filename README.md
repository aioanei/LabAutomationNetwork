Lab Architect & Dependency Manager

This is a Python application built with Tkinter that acts as a Knowledge Graph and Dependency Resolver for laboratory automation equipment. It allows users to manage an inventory of lab components, define complex, multi-level dependencies (simulating documentation), and use the Google Gemini AI to intelligently select the best parts for a specific project based on user requirements.

Features

Knowledge Graph Management: Tools are stored in the local lab_inventory.json file with multi-level dependencies (e.g., System -> Module -> Component -> Part -> Raw Material).

AI-Powered Project Building: The application uses the Gemini API to analyze design intents (e.g., "fast," "cheap," "ceramic parts") and selects the most appropriate components from your inventory to fulfill complex dependency trees.

Inventory Visualization: Browse your entire catalog of tools, categories, and their immediate requirements via the interactive Treeview GUI.

Deep Dependency Viewer: Click on any component to instantly see its full, recursive requirement chain in the log window.

JSON Persistence: Automatically loads and saves your entire tool database to lab_inventory.json.

🛠️ Prerequisites

To run this application, you need Python and the following libraries:

Python 3.8+

Tkinter (Usually included with standard Python installations)

Google Generative AI: For the core AI selection logic.

Python-Dotenv: To securely manage your API key.

Installation

You can install the required Python libraries using pip:

pip install google-generativeai python-dotenv


Setup and Configuration

The application requires a Gemini API key to use the intelligent building features.

1. API Key Setup

Create a file named .env in the same directory as lab_builder.py.

Add your Google AI Studio API key to this file, using the variable name GEMINI_API_KEY.

Example .env content:

GEMINI_API_KEY=AIzaSy...your...actual...key...here


2. Inventory Setup

The application looks for a file named lab_inventory.json in the same directory.

If you have the file: Ensure the lab_inventory.json file (containing your deeply nested tools) is present. The application will load it automatically on startup.

If you do not have the file: The application will start with an empty inventory. You can then use the "Add/Download Tool" button to manually input components and their dependency documentation.

▶️ How to Run

Navigate to the directory containing lab_builder.py and run it from your terminal:

python lab_builder.py


🚀 Usage Guide

1. Viewing Inventory

Upon launch, the left panel (Inventory Knowledge Graph) shows all loaded tools organized by Category.

To view a component's full dependency tree: Click on any item (e.g., 96-Channel Pipetting Head). The entire recursive requirement chain will be displayed in the Log & Visualization panel on the right.

2. Building a Project (AI Selection)

Click the "🏗️ Build Project (Gemini)" button.

System to Build: Enter the name of the top-level system you want to construct (e.g., Advanced Liquid Handler System). Note: The window pre-fills with an example from the provided JSON for quick testing.

Design Intent / Requirements: Provide a prompt detailing your constraints (e.g., "I need high speed," "It must be cheap," "Prioritize low-noise parts").

Click "Generate Configuration."

The application will use the Gemini model to traverse the dependencies in your inventory, making the best component selection at each step based on your intent, and then displaying the final, resolved Bill of Materials (BOM).
