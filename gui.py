import sqlite3
import os
import re

import json
import tkinter as tk
from tkinter import Menu, filedialog, Frame, Canvas, Scrollbar, Label, Entry, Button, simpledialog, PhotoImage, ttk

from PIL import Image, ImageTk
import pytesseract
from PIL import ImageOps, Image, ImageTk
import customtkinter as ctk
from paddleocr import PaddleOCR, draw_ocr
import threading
import shutil
import numpy
import datetime
import uuid
from itertools import groupby
import cv2
import json
import io
import numpy as np
from functools import partial
from dotenv import load_dotenv
import fitz
pytesseract.pytesseract.tesseract_cmd = r'.\tesseract_bin\tesseract.exe'
load_dotenv()

class KeyValueModelBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Key-Value Model Builder")
        self.geometry("1200x850")
        self.iconbitmap('favicon/favicon.ico')
        self.pdf_document = None
        self.current_page = 0
        self.total_pages = 0
        self.start_x, self.start_y = None, None
        self.rect = None
        self.show_zone_labels = True  # Add this line to control the visibility of labels names on zonal boxes
        self.templates_dir = "templates"
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir)

        #Google Vision
        self.credentials_folder = "Credentials"
        self.service_account_folder = os.path.join(self.credentials_folder, "ServiceAccount")
        self.api_folder = os.path.join(self.credentials_folder, "API")

        self.google_credentials_file_name_var = tk.StringVar()
        self.selected_google_credentials_file_path = ""
        self.google_api_key_var = tk.StringVar()
        self.google_api_key_name_var = tk.StringVar()

        self.ensure_google_credentials_folders()
        self.load_api_key()



        self.minsize(800, 600)
        self.zone_counter = 0
        self.deleted_zones = []
        self.init_ui()
        style = ttk.Style()
        style.configure('custom.TMenubutton', padding=0)
        style.configure('custom.TMenubutton.Label', font=('Helvetica', 8))
        self.ignore_next_release = False  # Flag to control zone creation
        self.canvas_scale = 1.0
        self.page_sizes = []
        self.progress_bars = {}
        self.zones_info = []
        os.makedirs("ocr_results", exist_ok=True)
        self.file_paths = {}
        self.create_database()
        self.document_database = self.load_document_database()
        self.model_database = self.load_models_database()
        self.populate_treeview_with_database()
        self.update_folder_sizes()
        self.apply_alternating_row_colors()
        self.initialize_ocr_engine()
        self.placeholder_labels = {}
        
        
        
        self.user_config_window = None
        self.model_config_window = None
        self.label_widgets = []
        self.new_label_widgets = []
        self.model_name = []
        global model_label_names
        model_label_names = []
        self.zone_overlap_var = tk.StringVar(value="0.35")
        

    def init_ui(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(expand=True, fill='both')
        
        self.notebook = ttk.Notebook(main_frame)
        self.document_files_list = ctk.CTkFrame(self.notebook)
        self.notebook.add(self.document_files_list, text='Document Files')
        self.document_viewer = ctk.CTkFrame(self.notebook)
        # self.notebook.add(self.document_viewer, text='File Viewer')

        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.create_document_files_tab(self.document_files_list)
        self.create_preload_images(self.document_viewer) 
        self.create_canvas(self.document_viewer)
        self.create_label_control_frame(self.document_viewer)
        self.create_menu_bar()
        self.create_status_bar(main_frame)

        main_frame.grid_rowconfigure(0, weight=1)  # Give notebook most of the space
        main_frame.grid_rowconfigure(1, weight=0)  # Status bar 
        main_frame.grid_columnconfigure(0, weight=1)

        self.ocr_engine = os.getenv('My_OCR_Engine', 'PaddleOCR')

    def initialize_ocr_engine(self):
        if self.ocr_engine == "PaddleOCR":
            self.initialize_paddleocr()
        elif self.ocr_engine == "Google_Vision":
            self.initialize_google_vision()
        elif self.ocr_engine == "EasyOCR":
            self.initialize_easyocr()

    def initialize_paddleocr(self):
        self.ocr = PaddleOCR(use_angle_cls=True, det=True, rec=True, rec_char_type='EN', det_db_box_thresh=0.5, det_db_thresh=0.3)

    def initialize_google_vision(self):
        self.google_vision_client = vision.ImageAnnotatorClient()

    def initialize_easyocr(self):
        self.easy_ocr = None #finish this
        print("EasyOCR Not Setup Yet")

    def create_database(self):
        conn = sqlite3.connect('document_database.sqlite')
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS documents
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT NOT NULL,
                    upload_date TEXT NOT NULL,
                    progress TEXT NOT NULL,
                    filetype TEXT,
                    page_count TEXT NOT NULL,
                    status TEXT NOT NULL,
                    size TEXT NOT NULL,
                    dimensions TEXT NOT NULL,
                    unique_id TEXT NOT NULL,
                    file_path TEXT NOT NULL)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS Models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT,
                    label_name TEXT,
                    label_type TEXT,
                    additional_type TEXT)''')
        
        # cursor.execute('''CREATE TABLE IF NOT EXISTS Pages (
        #             id INTEGER PRIMARY KEY AUTOINCREMENT,
        #             file_name TEXT NOT NULL,
        #             upload_date TEXT NOT NULL,
        #             progress TEXT NOT NULL,
        #             status TEXT NOT NULL,
        #             dimensions TEXT NOT NULL,
        #             file_unique_id TEXT NOT NULL,
        #             page_unique_id TEXT NOT NULL,
        #             file_path TEXT NOT NULL)''')
                    
        # cursor.execute('''CREATE TABLE IF NOT EXISTS document_pages
        #             (id INTEGER PRIMARY KEY AUTOINCREMENT,
        #             file_name TEXT NOT NULL,
        #             upload_date TEXT NOT NULL,
        #             filetype TEXT,
        #             page_count TEXT NOT NULL,
        #             status TEXT NOT NULL,
        #             size TEXT NOT NULL,
        #             dimensions TEXT NOT NULL,
        #             unique_id TEXT NOT NULL,
        #             file_path TEXT NOT NULL)''')
        conn.commit()
        conn.close()


    def adjust_columns(self, event=None):
        for col in self.document_list['columns']:
            self.document_list.column(col, width=tk.font.Font().measure(col.title()), stretch=tk.YES)
        self.document_list.update_idletasks()


    def load_document_database(self):
        try:
            conn = sqlite3.connect('document_database.sqlite')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM documents')
            document_rows = cursor.fetchall()
            conn.close()

            document_database = []
            for row in document_rows:
                itemId, file_name, upload_date, progress, filetype, page_count, status, size, dimensions, unique_id, file_path = row
                size_match = re.search(r"(\d+\.\d+)", size) if size is not None else None
                formatted_size = "{:.2f} MB".format(float(size_match.group(1))) if size_match else "N/A"
                document = {
                    'item_id': itemId,
                    'file_name': file_name,
                    'upload_date': upload_date,
                    'progress': progress,
                    'filetype': filetype,
                    'page_count': page_count,
                    'status': status,
                    'size': formatted_size,
                    'dimensions': dimensions,
                    'unique_id': unique_id,
                    'file_path': file_path,
                }
                document_database.append(document)
            return document_database
        except Exception as e:
            print(f"Error reading the document database: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def load_models_database(self):
        try:
            conn = sqlite3.connect('document_database.sqlite')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM models')
            model_rows = cursor.fetchall() 
            conn.close()
            
            models_database = []
            for row in model_rows:
                model_name, label_name, label_type, additional_type = row
                model = {
                    'model_name': model_name,
                    'label_name': label_name,
                    'label_type': label_type,
                    'additional_type': additional_type
                }
                models_database.append(model)
            return models_database
        except Exception as e:
            print(f"Error reading the models database: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def insert_document(self, document):
        try:
            conn = sqlite3.connect('document_database.sqlite')
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO documents
                        (file_name, upload_date, progress, filetype, page_count, status, size, dimensions, unique_id, file_path)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                        (document['file_name'], document['upload_date'], document['progress'], document['filetype'], document['page_count'], document['status'], document['size'], str(document['dimensions']), document['unique_id'], document['file_path']))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f'There was a problem inserting the document: {e}')
        finally:
            if conn:
                conn.close()


    def populate_treeview_with_database(self):
        for doc in self.document_database:
            self.document_list.insert('', 'end', values=(
                doc['file_name'],
                doc['upload_date'],
                doc['progress'],
                doc.get('filetype', 'N/A'),
                doc.get('page_count', 'N/A'),
                doc.get('status', 'N/A'),
                doc.get('size', 'N/A'),
                doc.get('dimensions', [0,0]),
                doc.get('unique_id', 'N/A'),
            ))
            self.file_paths[doc['file_name']] = doc['file_path']


    def create_document_files_tab(self, parent):
        self.button_frame = ctk.CTkFrame(parent)
        self.button_frame.pack(side=tk.TOP, fill=tk.X)
        import_btn = ctk.CTkButton(self.button_frame, text="Import", command=self.add_document)
        import_btn.pack(side=tk.LEFT, padx=5, pady=5)
        scan_btn = ctk.CTkButton(self.button_frame, text="Scan Document", command=self.scan_document)
        scan_btn.pack(side=tk.LEFT, padx=5, pady=10)
        self.selected_model = tk.StringVar(parent)
        self.model_option_menu = ctk.CTkOptionMenu(master=self.button_frame, variable=self.selected_model, values=self.get_model_names())
        self.model_option_menu.pack(side=tk.RIGHT, padx=10, pady=5)
        self.selected_model.set('Select Model')
        self.selected_model.trace("w", self.on_model_selected)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.Treeview", background="#E3E3E3", foreground="black", rowheight=25, fieldbackground="#E3E3E3")
        style.configure("Custom.Treeview.Heading", font=('Calibri', 10, 'bold'), relief="raised")
        style.map("Custom.Treeview", background=[('selected', 'lightblue')], foreground=[('selected', 'white')])
        self.document_list = ttk.Treeview(parent, style="Custom.Treeview", columns=('File Name', 'Upload Date', 'Progress', 'Filetype','Pages', 'Status', 'Size'), show='headings')
        self.document_list.heading('File Name', text='File Name')
        self.document_list.heading('Upload Date', text='Upload Date')
        self.document_list.heading('Progress', text='Progress')
        self.document_list.heading("Filetype", text="Filetype")
        self.document_list.heading("Pages", text="Pages")
        self.document_list.heading("Status", text="Status")
        self.document_list.heading("Size", text="Size")
        self.document_list.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.context_menu = tk.Menu(self.document_list, tearoff=0)
        self.context_menu.add_command(label="Scan", command=self.scan_document)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete", command=self.delete_document)
        
        self.document_list.bind("<Button-3>", self.show_context_menu)
        self.document_list.bind("<<TreeviewSelect>>", self.on_treeview_select)
        self.document_list.bind("<Double-1>", self.open_document)
        self.document_list.bind("<Configure>", self.adjust_columns)
        self.adjust_columns()


    def update_model_dropdown(self):
        """Updates the model dropdown with the latest model names from the database."""
        model_names = self.get_model_names()
        if hasattr(self, 'model_option_menu'):
            self.model_option_menu.destroy()
        self.model_option_menu = ctk.CTkOptionMenu(master=self.button_frame, variable=self.selected_model, values=model_names)
        self.model_option_menu.pack(side=tk.RIGHT, padx=5, pady=5)
        if not self.selected_model.get() or self.selected_model.get() == 'Select Model':
            self.selected_model.set('Select Model')
        self.selected_model.trace("w", self.on_model_selected)

    def get_model_names(self):
        model_names = []
        try:
            conn = sqlite3.connect('document_database.sqlite')
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT model_name FROM Models')
            rows = cursor.fetchall()
            for row in rows:
                model_name = row[0]  # model_name is the first element in the row
                if model_name:  # Check if model_name is not None or empty
                    model_names.append(model_name)
            conn.close()
        except Exception as e:
            print("Error retrieving model names:", e)
        finally:
            if conn:
                conn.close()
        return model_names
    
    def on_model_selected(self, *args):
        selected_model = self.selected_model.get()
        print(f"Model selected: {selected_model}")
        self.model_name = selected_model
        self.clear_model_label_fields()
        # self.retrieve_model_labels(selected_model)
        model_labels = self.retrieve_model_labels(selected_model)
        self.generate_model_labels(model_labels)

    def retrieve_model_labels(self, model_name):
        try:
            global model_label_names
            print('getting DB connection')
            conn = sqlite3.connect('document_database.sqlite')
            cursor = conn.cursor()
            cursor.execute("SELECT label_name, label_type, additional_type FROM Models WHERE model_name = ?", (model_name,))
            model_labels = cursor.fetchall()
            conn.close()
            # self.add_model_label_field(model_labels)
            print(model_labels)
            model_label_names.clear()
            model_label_names.extend([label[0] for label in model_labels])
            return model_labels
        except Exception as e:
            print(f'There was an issue getting model info from DB:: {e}')
            return
        finally:
            if conn:
                conn.close()
    
    def generate_model_labels(self, model_labels):
        self.add_model_label_field(model_labels)
        
    def clear_model_label_fields(self):
        """Clears existing model label fields from the UI."""
        try:
            if hasattr(self, 'label_widgets'):
                for widget in self.label_widgets:
                    if widget.get('frame'):
                        widget['frame'].destroy()
                self.label_widgets.clear()
        except Exception as e:
            print(f'Error Removing Previous labels: {e}')

    def add_model_label_field(self, model_labels):
        print('adding saved model labels to GUI')
        for label_name, label_type, additional_type in model_labels:
            color = self.get_unique_color()
            label_info_frame = ctk.CTkFrame(self.results_scrollable_frame)
            label_info_frame.pack(fill='x', expand=True, pady=5, padx=2)

            top_frame = ctk.CTkFrame(label_info_frame, fg_color="transparent")
            top_frame.pack(side="top", fill="x", pady=5, padx=5)

            colorLineIndicator = ctk.CTkProgressBar(master=top_frame, orientation="vertical", fg_color=color, border_color=color, progress_color=color, height=30)
            colorLineIndicator.set(1)
            colorLineIndicator.pack(side="left", padx=(0, 3), pady=0)

            label_label = ctk.CTkLabel(top_frame, text=f"{label_name}:", font=("Helvetica", 12.5))
            label_label.pack(side="left", padx=0)

            label_entry = ctk.CTkEntry(top_frame, font=("Helvetica", 12))
            label_entry.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=2)

            label_type_frame = ctk.CTkFrame(label_info_frame, fg_color="transparent")
            label_type_frame.pack(side="top", fill="x", expand=True, pady=5, padx=5)

            label_type_label = ctk.CTkLabel(label_type_frame, text="Type:", font=("Helvetica", 12.5))
            label_type_label.pack(side="left", padx=5, pady=(0, 1))

            field_type_dropdown = ctk.CTkLabel(label_type_frame, text=label_type)
            field_type_dropdown.pack(side="left", padx=5)

            if additional_type:
                additional_field_type_dropdown = ctk.CTkLabel(label_type_frame, text="(" + additional_type + ")")
                additional_field_type_dropdown.pack(side="right", padx=5)

            # Store the label information in a structured way
            label_info = {
                'frame': label_info_frame,
                'label_name': label_label,
                'entry': label_entry,
                'field_type': label_type,
                'color': color,
                'label_type': label_type,
                'additional_type': additional_type,
            }
            
            self.label_widgets.append(label_info)


    def show_file_viewer_tab(self):
        """add/unhide the 'File Viewer' tab to the notebook."""
        if self.document_viewer not in self.notebook.tabs():
            self.notebook.add(self.document_viewer, text='File Viewer')

    def open_document(self, event):
        self.show_file_viewer_tab()
        item_id = self.document_list.identify_row(event.y)
        selected_item = self.document_list.focus()
        if item_id:
            item = self.document_list.item(selected_item)
            file_name, upload_date, progress, filetype, pages, status, size, dimensions, unique_id = item['values']
            self.current_unique_id = unique_id
            target_directory = self.get_file_path(unique_id)
            if target_directory and os.path.isdir(target_directory):
                self.png_files = [os.path.join(target_directory, f"{file_name}_page_{page_num}.png") for page_num in range(1, int(pages) + 1)]
                self.current_page = 0
                self.total_pages = len(self.png_files)
                self.notebook.select(self.document_viewer)
                self.display_page()
                self.refresh_thumbnails()
            else:
                print(f"Open Document - File path not found for {file_name}")
            if progress != "100%":
                print(f"Document {file_name} is not yet fully processed. Current progress: {progress}")

    def scan_document(self, item_id=None):
        if item_id is None:
            item_id = self.document_list.focus()
        if item_id:
            item = self.document_list.item(item_id)
            try:
                file_name, upload_date, progress, filetype, pages, status, size, dimensions, unique_id = item['values']
                if progress == "100%":
                    print(f"File {file_name} has already been scanned.")
                    return
            except ValueError as e:
                print(f"Error unpacking item values:: {e}. Item values: {item['values']}")
                return
            self.update_document_data(unique_id, status="Scanning")

            def start_ocr_process():
                try:
                    target_directory = self.get_file_path(unique_id)
                    if target_directory and os.path.isdir(target_directory):
                        for page_num in range(1, pages + 1):
                            png_file = f"{file_name}_page_{page_num}.png"
                            file_path = os.path.join(target_directory, png_file)
                            self.perform_ocr_with_progress(page_num, file_name, pages, file_path, unique_id, item_id)
                    else:
                        print(f"Scan document - Target directory not found for {file_name}")
                except Exception as e:
                    print(f"There was an exception: {e}")
                    self.update_document_data(unique_id, status="New")
            try:
                ocr_thread = threading.Thread(target=start_ocr_process)
                ocr_thread.start()
            except Exception as e:
                    print(f"There was an exception during threading: {e}")
                    self.update_document_data(unique_id, status="New")
        else:
            print("No document selected")
            

    def delete_document_from_database(self, unique_id):
        try:
            conn = sqlite3.connect('document_database.sqlite')
            cursor = conn.cursor()
            cursor.execute('''DELETE FROM documents WHERE unique_id = ?''', (unique_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f'there was an error deleting the document: {e}')
        finally:
            if conn:
                conn.close()

    def update_document_in_database(self, unique_id, **kwargs):
        try:
            conn = sqlite3.connect('document_database.sqlite')
            cursor = conn.cursor()
            update_fields = ', '.join([f"{key} = ?" for key in kwargs.keys()])
            update_values = list(kwargs.values())
            update_values.append(unique_id)
            cursor.execute(f"UPDATE documents SET {update_fields} WHERE unique_id = ?", update_values)
            conn.commit()
        except Exception as e:
            print(f"Error updating document in database: {e}")
        finally:
            if conn:
                conn.close()

    def delete_document(self):
        selected_item = self.document_list.selection()
        if selected_item:
            item_id = selected_item[0]
            unique_id = self.document_list.item(item_id, 'values')[-1] 
            for i, doc in enumerate(self.document_database):
                if doc['unique_id'] == unique_id:
                    target_directory = os.path.join("ocr_results", unique_id)
                    if os.path.exists(target_directory):
                        shutil.rmtree(target_directory) 
                    self.delete_document_from_database(unique_id)
                    break
            self.document_list.delete(item_id)
            self.update_document_database_from_treeview()
            self.document_database = [doc for doc in self.document_database if doc["unique_id"] != unique_id]
            self.apply_alternating_row_colors()
        else:
            print("No document selected")

    def update_document_database_from_treeview(self):
        for item in self.document_list.get_children():
            item_values = self.document_list.item(item, 'values')
            unique_id = item_values[-1]
            for doc in self.document_database:
                if doc['unique_id'] == unique_id:
                    doc['item_id'] = item
                    break

    def show_context_menu(self, event):
        row_id = self.document_list.identify_row(event.y)
        if row_id:
            self.document_list.selection_set(row_id)
            self.selected_item_id = row_id
            try:
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()
    

    def on_treeview_select(self, event):
        selected_item = self.document_list.selection()
        if selected_item:
            self.selected_item_id = selected_item[0]


    def get_file_path(self, unique_id):
        document = next((doc for doc in self.document_database if doc['unique_id'] == unique_id), None)
        if document:
            return document.get('file_path')
        return None
    
    def perform_ocr_with_progress(self, page_num, file_name, pages, file_path, unique_id, item_id):
            if os.path.exists(file_path):
                print(f"Starting OCR for {file_path}")
                #self.update_document_data(unique_id, status="Scanning")
            if not file_path:
                print(f"OCR W/ Progress - File path not found for unique ID {unique_id}")
                return
            all_page_results = {}
            total_pages = pages
            try:
                print(f"Processing page number: {page_num}; total pages: {total_pages}")
                img = Image.open(file_path)
                img = self.scale_image_if_large(img)
                original_dimensions = (img.width, img.height) 
                cv_image = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                page_ocr_results = self.perform_ocr_on_image(cv_image)
                if page_ocr_results:
                    all_page_results[f"Page_{page_num}"] = page_ocr_results
                    self.save_ocr_results_for_page(file_name, unique_id, page_num, page_ocr_results)
                else:
                    print(f"No OCR results for page {page_num + 1}, skipping.")

                self.update_folder_sizes()
                progress = (page_num) / total_pages * 100
                self.update_document_data(unique_id, progress=progress, dimensions=original_dimensions)
                
                if progress == 100:
                    self.update_document_data(unique_id, status="To Review")
            except Exception as e:
                print(f"OCR Performance fucked up:: {e}")
                progress = 0
                self.update_document_data(unique_id, progress=progress, dimensions=original_dimensions, status="New")



    def perform_ocr_on_image(self, cv_image):
        if self.ocr_engine == 'PaddleOCR':
            return self.perform_paddleocr_on_image(cv_image)
        elif self.ocr_engine == 'Google Vision':
            return self.perform_google_vision_on_image(cv_image)
        else:
            print("Unsupported OCR engine.")
            return None
        

    def get_total_pages(self, file_path):
        try:
            if not os.path.exists(file_path) or not os.path.isdir(file_path):
                print(f"Directory not found at {file_path}")
                return 0
            png_files = [f for f in os.listdir(file_path) if f.endswith('.png')]
            total_pages = len(png_files)
            return total_pages
        except Exception as e:
            print(f"Error while getting total pages: {e}")
            return 0
    

    def scale_image_if_large(self, image, max_pixels=178956970):
        if isinstance(image, Image.Image):
            if image.width * image.height > max_pixels:
                print('Image over max pixels')
                scale_factor = (max_pixels / (image.width * image.height)) ** 0.5
                new_width = int(image.width * scale_factor)
                new_height = int(image.height * scale_factor)
                return image.resize((new_width, new_height), Image.ANTIALIAS)
        else:
            print(f"Unexpected file format for image")
        return image
    

    def make_serializable(self, ocr_results):
        serializable_results = []
        for result in ocr_results:
            serializable_result = {
                'text': result['text'],
                'bbox': result['bbox'],
                'confidence': result['confidence']
            }
            serializable_results.append(serializable_result)
        return serializable_results
    
    def start_ocr_process_for_all(self):
        for item_id in self.document_list.get_children():
            self.scan_document(item_id)


    def save_ocr_results_for_page(self, file_name, unique_id, page_num, ocr_results):
        results_file_path = f'./ocr_results/{unique_id}/'
        if not os.path.exists(results_file_path):
            os.makedirs(results_file_path)
        output_filename = os.path.join(results_file_path, f"{file_name}_page_{page_num}.json")
        with open(output_filename, 'w') as outfile:
            json.dump(ocr_results, outfile, indent=4)
            
    def get_folder_size(self, folder_path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(folder_path):
            for f in filenames:
                file_path = os.path.join(dirpath, f)
                if os.path.isfile(file_path):
                    total_size += os.path.getsize(file_path)
        return total_size


    def update_folder_sizes(self):
        for doc in self.document_database:
            folder_path = os.path.join("ocr_results", doc['unique_id'])
            folder_size = self.get_folder_size(folder_path)
            size_in_mb = folder_size / (1024 * 1024)
            doc['size'] = f"{size_in_mb:.2f} MB"
            if self.document_list.exists(doc['item_id']):
                self.document_list.set(doc['item_id'], 'Size', doc['size'])


    def add_document(self):
        file_paths = filedialog.askopenfilenames(filetypes=[
            ("All files", "*.pdf;*.jpeg;*.jpg;*.png"),
            ("PDF files", "*.pdf"),
            ("JPEG files", "*.jpeg"),
            ("JPG files", "*.jpg"),
            ("PNG files", "*.png")
        ])
        if file_paths:
            for file_path in file_paths:
                self.process_single_document(file_path)
            self.apply_alternating_row_colors()

    def process_single_document(self, file_path):
        file_name = os.path.basename(file_path)
        base_name, file_extension = os.path.splitext(file_name)
        file_extension = file_extension.lower()
        if any(doc['file_name'] == base_name for doc in self.document_database):
            print(f"Document '{base_name}' is already uploaded. Skipping.")
            return
        unique_id = str(uuid.uuid4())
        target_directory = os.path.join("ocr_results", unique_id)
        os.makedirs(target_directory, exist_ok=True)
        target_path = os.path.join(target_directory)
        filetype = "Unknown"
        page_count = 0
        dimensions = [0,0]
        if file_extension == '.pdf':
            page_count, dimensions, png_paths = self.convert_to_png(file_path, target_directory, base_name)
            filetype = "PDF"
        elif file_extension in ['.png', '.jpeg', '.jpg']:
            shutil.copy(file_path, target_path)
            filetype = file_extension[1:].upper()
            if file_extension == '.png':
                new_file_name = f"{base_name}_page_1{file_extension}"
                target_file_path = os.path.join(target_directory, new_file_name)
                shutil.copy(file_path, target_file_path)
                filetype = file_extension[1:].upper()
                page_count = len([f for f in os.listdir(target_directory) if f.endswith('.png')])
                img = Image.open(file_path)
                dimensions = [img.width, img.height]
            elif file_extension == '.jpeg':
                page_count = len([f for f in os.listdir(target_directory) if f.endswith('.jpeg')])
                img = Image.open(file_path)
                dimensions = [img.width, img.height]
            elif file_extension == '.jpg':
                page_count = len([f for f in os.listdir(target_directory) if f.endswith('.jpg')])
                img = Image.open(file_path)
                dimensions = [img.width, img.height]
            else:
                print(f"File type: '{file_extension}' not supported.")
                return

        folder_size = self.get_folder_size(target_directory)
        size_in_mb = folder_size / (1024 * 1024)
        upload_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%p")
        item_id = self.document_list.insert('', 'end', values=(base_name, upload_date, "0%", filetype, str(page_count), "New", f"{size_in_mb:.2f} MB", dimensions, unique_id))
        self.insert_document({
            'file_name': base_name,
            'upload_date': upload_date,
            'progress': "0%",
            'item_id': item_id,
            'file_path': target_path,
            'filetype': filetype,
            'page_count': str(page_count),
            'status': "To Review",
            'size': f"{size_in_mb:.2f} MB",
            'dimensions': dimensions,
            'unique_id': unique_id # Must stay last field
        })
        self.update_document_data(unique_id, page_count=str(page_count), status="New", size=size_in_mb, filetype=filetype)
        self.apply_alternating_row_colors()
        self.document_database = self.load_document_database()
        self.document_list.update_idletasks() # Update UI immediately after processing each document
            
    def convert_to_png(self, source_path, target_directory, base_name, dpi=600):
        try:
            file_extension = os.path.splitext(source_path)[1].lower()
            png_paths = []
            dimensions = [0, 0]
            if file_extension == '.pdf':
                doc = fitz.open(source_path)
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    mat = fitz.Matrix(dpi / 72, dpi / 72)  # Transformation matrix for higher DPI
                    pix = page.get_pixmap(matrix=mat)  # Apply the transformation
                    if page_num == 0:
                        dimensions = [pix.width, pix.height]
                    png_path = os.path.join(target_directory, f"{base_name}_page_{page_num + 1}.png")
                    pix.save(png_path)
                    png_paths.append(png_path)
                doc.close()
            elif file_extension == '.jpg' or file_extension == '.jpeg':
                img = Image.open(source_path)
                dimensions = [img.width, img.height]
                png_path = os.path.join(target_directory, os.path.splitext(os.path.basename(source_path))[0] + ".png")
                img.save(png_path, "PNG")
                png_paths.append(png_path)
            return len(png_paths), dimensions, png_paths
        except Exception as e:
            print(f"Error converting file to PNG: {e}")
            return 0, [], [0,0]
    
    def apply_alternating_row_colors(self):
        for i, item in enumerate(self.document_list.get_children()):
            self.document_list.tag_configure('evenrow', background='#FFFFFF')
            self.document_list.tag_configure('oddrow', background='#F0F0F0')
            if i % 2 == 0:
                self.document_list.item(item, tags=('evenrow',))
            else:
                self.document_list.item(item, tags=('oddrow',))

    def update_document_data(self, unique_id, progress=None, filetype=None, page_count=None, status=None, size=None, dimensions=None):
        for item in self.document_list.get_children():
            item_values = self.document_list.item(item, 'values')
            if item_values[-1] == unique_id:
                item_id = item
                # print(f"Updating Treeview item: {item_id}")
                update_kwargs = {}
                if progress is not None:
                    self.document_list.set(item_id, 'Progress', f"{int(progress)}%")
                    update_kwargs['progress'] = f"{int(progress)}%"
                if filetype is not None:
                    self.document_list.set(item_id, 'Filetype', filetype)
                    update_kwargs['filetype'] = filetype
                if page_count is not None:
                    self.document_list.set(item_id, 'Pages', str(page_count))
                    update_kwargs['page_count'] = str(page_count)
                if status is not None:
                    self.document_list.set(item_id, 'Status', status)
                    update_kwargs['status'] = status
                if size is not None:
                    formatted_size = f"{size:.2f} MB"
                    self.document_list.set(item_id, 'Size', formatted_size)
                    update_kwargs['size'] = formatted_size
                if dimensions:
                    formatted_dimensions = f"[{dimensions[0]},{dimensions[1]}]"  # Format as '[width,height]'
                    update_kwargs['dimensions'] = formatted_dimensions

                self.update_document_in_database(unique_id, **update_kwargs)
                return
        else:
            print(f"File {unique_id} not found in Treeview")

    def save_document_database(self):
        with open(self.document_database_path, 'w') as db_file:
            json.dump(self.document_database, db_file, indent=4)


    def load_pdf_for_json_output(self, file_path):
        self.pdf_document = fitz.open(file_path)
        self.total_pages = len(self.pdf_document)
        self.page_sizes = [page.rect.br - page.rect.tl for page in self.pdf_document]  
        self.current_page = 0


    def load_json_data(self, file_path, page_num, unique_id):
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        json_directory = os.path.join("ocr_results", unique_id)  
        json_filename = f"{base_name}.json"
        json_path = os.path.join(json_directory, json_filename)
        try:
            with open(json_path, 'r') as f:
                self.current_json_data = json.load(f)
        except FileNotFoundError:
            print(f"JSON file not found for {file_path}, page {page_num + 1}")
            self.current_json_data = {}

    def create_menu_bar(self):
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Import", command=self.select_pdf)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        template_menu = tk.Menu(menu_bar, tearoff=0)
        template_menu.add_command(label="Save Template", command=self.save_template)
        template_menu.add_separator()
        template_menu.add_command(label="Load Template", command=self.load_template)
        template_menu.add_separator()
        template_menu.add_command(label="New Template", command=self.new_template)

        model_menu = tk.Menu(menu_bar, tearoff=0)
        model_menu.add_command(label="New", command=self.open_model_config)
        
        user_config_menu = tk.Menu(menu_bar, tearoff=0)
        user_config_menu.add_command(label="Config", command=self.open_user_config)

        menu_bar.add_cascade(label="File", menu=file_menu)
        menu_bar.add_cascade(label="Templates", menu=template_menu)
        menu_bar.add_cascade(label="Model", menu=model_menu)
        menu_bar.add_cascade(label="Config", menu=user_config_menu)
        self.config(menu=menu_bar)
    
    def new_template(self):
        self.clear_zones()


    def open_user_config(self):
        if self.user_config_window is not None and not self.user_config_window.winfo_exists():
            self.user_config_window = None

        if self.user_config_window is None:
            self.user_config_window = tk.Toplevel(self)
            self.user_config_window.title("User Configuration")
            self.user_config_window.geometry("650x460")

            # Show OCR Engine Zones switch
            ctk.CTkLabel(self.user_config_window, text="This Page Does Not Work Yet").grid(row=0, column=1, columnspan=2, padx=10, pady=(20, 0), sticky="w")
            show_zones_var = ctk.StringVar(value="on")
            show_zones_switch_label = ctk.CTkLabel(self.user_config_window, text="Show OCR Engine Zones")
            show_zones_switch_label.grid(row=1, column=0, padx=10, pady=10, sticky="w")
            show_zones_switch = ctk.CTkSwitch(self.user_config_window, text="", variable=show_zones_var, onvalue="on", offvalue="off", state="disabled",)
            show_zones_switch.grid(row=1, column=1, padx=10, pady=10, sticky="w")

            # OCR Engine dropdown with label
            ctk.CTkLabel(self.user_config_window, text="Select OCR Engine").grid(row=2, column=0, padx=10, pady=(20, 0), sticky="w")
            ocr_engines = ["PaddleOCR", "Google Vision", "EasyOCR", "Tesseract"]
            ocr_engine_dropdown = ctk.CTkComboBox(self.user_config_window, values=ocr_engines, variable=self.ocr_engine)
            ocr_engine_dropdown.set(self.ocr_engine)
            ocr_engine_dropdown.grid(row=2, column=1, padx=10, pady=(20,0), sticky="w")

            # Zone Overlap entry field with label
            ctk.CTkLabel(self.user_config_window, text="Zone Overlap").grid(row=3, column=0, padx=10, pady=(20, 0), sticky="w")
            zone_overlap_entry = ctk.CTkEntry(self.user_config_window, textvariable=self.zone_overlap_var, placeholder_text="Ex. 0.35")
            zone_overlap_entry.grid(row=3, column=1, padx=10, pady=(20,0), sticky="w")

            # Google Vision Credentials file upload with label
            ctk.CTkLabel(self.user_config_window, text="Upload Google Credentials").grid(row=4, column=0, padx=10, pady=(20, 0), sticky="w")
            placeholder = self.google_credentials_file_name_var.get() if self.google_credentials_file_name_var.get() else "Ex. Google Vision Creds"
            ctk.CTkEntry(self.user_config_window, placeholder_text=placeholder).grid(row=4, column=1, padx=10, pady=(20,0), sticky="w")
            ctk.CTkButton(self.user_config_window, text="Upload JSON", command=self.upload_google_creds_file).grid(row=4, column=2, padx=10, pady=(20,10), sticky="w")

            # Google Vision Credentials API Key entry with label
            ctk.CTkLabel(self.user_config_window, text="or").grid(row=5, column=0)
            ctk.CTkLabel(self.user_config_window, text="Google Vision API Key Name").grid(row=6, column=0, padx=10, pady=(10, 0), sticky="w")
            ctk.CTkEntry(self.user_config_window, textvariable=self.google_api_key_name_var).grid(row=6, column=1, padx=10, pady=(10, 0), sticky="w")

            ctk.CTkLabel(self.user_config_window, text="Google Vision API Key").grid(row=7, column=0, padx=10, pady=(20, 0), sticky="w")
            ctk.CTkEntry(self.user_config_window, textvariable=self.google_api_key_var).grid(row=7, column=1, padx=10, pady=(20, 0), sticky="w")


            #AIzaSyDQ_l6fX15_QpXLTZYOwz3-oS08i4klUg4
            
            # Submit Config Changes
            ctk.CTkLabel(self.user_config_window, text="").grid(row=8, column=0)
            ctk.CTkButton(self.user_config_window, text="Submit", command=lambda: self.save_credentials(self.google_credentials_file_name_var.get())).grid(row=9, column=1, padx=10, pady=10, sticky="w")
        else:
            self.user_config_window.lift()


    def upload_google_creds_file(self):
        self.selected_google_credentials_file_path = filedialog.askopenfilename(title="Select Google Vision Credentials JSON", filetypes=[("JSON files", "*.json")])
        if self.selected_google_credentials_file_path:  
            file_name = os.path.basename(self.selected_google_credentials_file_path)
            self.google_credentials_file_name_var.set(file_name)

    def ensure_google_credentials_folders(self):
        os.makedirs(self.service_account_folder, exist_ok=True)
        os.makedirs(self.api_folder, exist_ok=True)

    def save_google_credentials(self, file_name):
        if self.selected_google_credentials_file_path:
            destination_path = os.path.join(self.service_account_folder, file_name)
            shutil.copy(self.selected_google_credentials_file_path, destination_path)
            print(f"File saved as: {destination_path}")
        else:
            print("No file selected to save.")

    def save_api_key(self):
        api_key_data = {
            'name': self.google_api_key_name_var.get(),
            'key': self.google_api_key_var.get()
        }
        api_key_path = os.path.join(self.api_folder, "api_key.json")
        with open(api_key_path, 'w') as f:
            json.dump(api_key_data, f)

    def load_api_key(self):
        api_key_path = os.path.join(self.api_folder, "api_key.json")
        if os.path.exists(api_key_path):
            with open(api_key_path, 'r') as f:
                api_key_data = json.load(f)
                self.google_api_key_name_var.set(api_key_data.get('name', ''))
                self.google_api_key_var.set(api_key_data.get('key', ''))
        
    def open_model_config(self):
        if self.model_config_window is not None and not self.model_config_window.winfo_exists():
            self.model_config_window = None

        if self.model_config_window is None:
            self.model_config_window = tk.Toplevel(self)
            self.model_config_window.title("Model Configuration")
            self.model_config_window.geometry("600x425")
            ctk.CTkLabel(self.model_config_window, text="Model Name:").grid(row=0, column=0, padx=(20,0), pady=10, sticky="w")
            model_name_var = tk.StringVar()
            ctk.CTkEntry(self.model_config_window, textvariable=model_name_var, width=200).grid(row=0, column=1, pady=10, sticky="w")
            ctk.CTkLabel(self.model_config_window, text="Label Name").grid(row=1, column=0, padx=(20,0), pady=2, sticky="w")
            ctk.CTkLabel(self.model_config_window, text="Value Type").grid(row=1, column=1, padx=0, pady=2, sticky="w")
            self.labels_frame = ctk.CTkFrame(self.model_config_window)
            self.labels_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")
            ctk.CTkButton(self.model_config_window, text="Add Label", command=self.model_config_add_label).grid(row=3, column=0, columnspan=2, padx=10, pady=10, sticky="w")
            ctk.CTkButton(self.model_config_window, text="Submit", command=lambda: self.save_model_config(model_name_var.get())).grid(row=4, column=1, padx=10, pady=10, sticky="w")
            self.model_config_add_label()

        else:
            self.model_config_window.lift()
            
    def model_config_add_label(self):
        row = len(self.labels_frame.winfo_children()) // 4
        label_types = ["Text", "Number", "Date", "Currency", "Barcode", "E-mail", "Address", "Location", "Phone Number", "URL"]
        label_name_var = tk.StringVar()
        label_name_entry = ctk.CTkEntry(self.labels_frame, textvariable=label_name_var)
        label_type_var = tk.StringVar(value=label_types[0])
        label_type_dropdown = ctk.CTkComboBox(self.labels_frame, values=label_types, variable=label_type_var)
        additional_options_var = tk.StringVar(value="")
        additional_options_dropdown = ctk.CTkComboBox(self.labels_frame, values=[], variable=additional_options_var)
        label_name_entry.grid(row=row, column=0, padx=10, pady=2, sticky="w")
        label_type_dropdown.grid(row=row, column=1, padx=10, pady=2, sticky="w")
        additional_options_dropdown.grid(row=row, column=2, padx=10, pady=2, sticky="w")
        additional_options_dropdown.lower()
        additional_options_dropdown.lower()  
        if not hasattr(self, 'additional_options_widgets'):
            self.additional_options_widgets = {}
        self.additional_options_widgets[row] = additional_options_dropdown
        label_type_dropdown.configure(command=lambda selected_value: self.update_additional_options(row, label_type_var.get()))

        remove_button = ctk.CTkButton(self.labels_frame, text="X", width=25, command=lambda: self.remove_label(row))
        remove_button.grid(row=row, column=3, padx=10, pady=2, sticky="w")
        
        if not hasattr(self, 'new_label_widgets'):
            self.new_label_widgets = []
        self.new_label_widgets.append({
            "name_entry": label_name_entry,
            "type_dropdown": label_type_dropdown,
            "options_dropdown": additional_options_dropdown
        })

        
    def update_additional_options(self, row, label_type):
        additional_options_dropdown = self.additional_options_widgets[row]
        if label_type == "Number":
            options = ["Integer", "Float", "Percentage", "ANY"]
        elif label_type == "Date":
            options = ["YYYY-MM-DD", "MM/DD/YYYY", "DD-MM-YYYY", "ANY"]
        elif label_type == "Currency":
            options = ["USD", "EUR", "GBP", "JPY", "ANY"]
        else:
            options = []
        if options:
            additional_options_dropdown.configure(values=options)
            additional_options_dropdown.set(options[0])
            additional_options_dropdown.lift()
        else:
            additional_options_dropdown.lower()
            
    def remove_label(self, row):
        for widget in self.labels_frame.grid_slaves(row=row):
            widget.destroy()
        for widget in self.labels_frame.winfo_children():
            grid_info = widget.grid_info()
            if grid_info["row"] > row:
                widget.grid(row=grid_info["row"], column=grid_info["column"])
        if row in self.additional_options_widgets:
            del self.additional_options_widgets[row]

    def save_model_config(self, model_name):
        try:
            # Database setup
            conn = sqlite3.connect('document_database.sqlite') 
            cursor = conn.cursor()

            for widgets in self.new_label_widgets:
                label_name = widgets['name_entry'].get()
                label_type_value = widgets['type_dropdown'].get()
                additional_type_value = widgets['options_dropdown'].get() if widgets['options_dropdown'].winfo_ismapped() else ''
                cursor.execute('''
                    INSERT INTO Models (model_name, label_name, label_type, additional_type)
                    VALUES (?, ?, ?, ?)
                ''', (model_name, label_name, label_type_value, additional_type_value))
            conn.commit()
            conn.close()
            print("Model configuration saved to database.")
            self.model_database
            self.update_model_dropdown()
            if self.model_config_window is not None:
                self.model_config_window.destroy()
                self.model_config_window = None
        except Exception as e:
            print("Error saving model configuration:", e)
        finally:
            if conn:
                conn.close()

    
    
    def save_template(self):
        template_name = simpledialog.askstring("Save Template", "Enter Template Name:")
        if template_name:
            current_page_size = self.page_sizes[self.current_page]
            template_data = []
            for zone in self.zones_info:
                if zone['rect']:
                    coords = self.canvas.coords(zone['rect'])
                    rel_coords = [
                        coords[0] / self.original_pdf_page_size[0], coords[1] / self.original_pdf_page_size[1],
                        coords[2] / self.original_pdf_page_size[0], coords[3] / self.original_pdf_page_size[1]
                    ]
                    template_data.append({
                        'zone_name': zone['entry'].get(),
                        'field_type': zone['field_type'].get(),
                        'coordinates': rel_coords
                    })

            template_file_path = os.path.join(self.templates_dir, f"{template_name}.json")
            with open(template_file_path, 'w') as file:
                json.dump(template_data, file)

    def get_template_names(self):
        if not os.path.exists(self.templates_dir):
            return []
        return [f for f in os.listdir(self.templates_dir) if f.endswith('.json')]

    def load_template(self):
        template_names = self.get_template_names()
        if not template_names:
            print("No templates available.")
            return
        select_window = tk.Toplevel(self)
        select_window.title("Select a Template")
        selected_template = tk.StringVar(select_window)
        selected_template.set(template_names[0])
        ctk.CTkOptionMenu(master=select_window, variable=selected_template, values=template_names).pack()
        load_button = ctk.CTkButton(select_window, text="Load Template",
                                command=lambda: self.apply_selected_template(selected_template.get(), select_window))
        load_button.pack()

    def apply_template(self, template_data):
        # if not self.pdf_document or self.current_page >= self.total_pages:
        #     print("No PDF document loaded or invalid page number.")
        #     return
        current_page_size = self.page_sizes[self.current_page]
        self.clear_zones()
        current_page_size = self.page_sizes[self.current_page]
        for zone_data in template_data:
            scaled_coords = [
                zone_data['coordinates'][0] * current_page_size[0], zone_data['coordinates'][1] * current_page_size[1],
                zone_data['coordinates'][2] * current_page_size[0], zone_data['coordinates'][3] * current_page_size[1]
            ]
            self.add_zone_field(zone_name=zone_data['zone_name'], coordinates=scaled_coords)

    def apply_selected_template(self, template_name, window):
        template_path = os.path.join(self.templates_dir, template_name)
        with open(template_path, 'r') as file:
            template_data = json.load(file)
        self.apply_template(template_data)
        window.destroy()

    def create_status_bar(self, parent):
        self.status_bar = tk.Label(parent, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=1, column=0, sticky="ew")

    def create_canvas(self, parent):
        self.canvas_frame = ctk.CTkFrame(parent)
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.canvas_frame, cursor="crosshair", xscrollincrement=1, yscrollincrement=1)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)


    def create_preload_images(self, parent):
        self.preload_frame = ctk.CTkScrollableFrame(parent)
        self.preload_frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 0))
        self.load_placeholders_or_empty(self.preload_frame)

    def load_placeholders_or_empty(self, scrollable_frame):
        ''' prepare the frame for future thumbnails '''
        pass

    def refresh_thumbnails(self):
        if hasattr(self, 'preload_frame'):
            for widget in self.preload_frame.winfo_children():
                widget.destroy()
            self.load_thumbnails(self.preload_frame)

    def load_thumbnails(self, scrollable_frame):
        try:
            image_paths = self.find_image_paths()
            self.placeholder_refs = []  # Make sure placeholder list is cleared or initialized
            for _ in image_paths:
                placeholder = tk.Label(scrollable_frame, text="Loading...", cursor="wait")
                placeholder.pack(padx=5, pady=5, side=tk.TOP)
                self.placeholder_refs.append(placeholder)
            threading.Thread(target=self.load_thumbnails_background, args=(scrollable_frame, image_paths), daemon=True).start()
        except Exception as e:
            print(f'There was an error loading thumbnails: {e}')

    def load_thumbnails_background(self, scrollable_frame, image_paths):
        for index, path in enumerate(image_paths):
            try:
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img)
                    if img.width > img.height:
                        base_width = 150
                        w_percent = (base_width / float(img.width))
                        h_size = int((float(img.height) * float(w_percent)))
                        img = img.resize((base_width, h_size), Image.Resampling.BOX)
                    else:
                        base_height = 200
                        h_percent = (base_height / float(img.height))
                        w_size = int((float(img.width) * float(h_percent)))
                        img = img.resize((w_size, base_height), Image.Resampling.BOX)
                    photo = ImageTk.PhotoImage(img)
                    self.schedule_thumbnail_update(scrollable_frame, index, photo, path)
            except Exception as e:
                print(f'There was an error loading a thumbnail: {e}')

    def schedule_thumbnail_update(self, scrollable_frame, index, photo, path):
        def _update():
            try:
                placeholder = self.placeholder_refs[index] # Directly replace the placeholder at the given index
                placeholder.config(image=photo, text="", cursor="hand2")  # Replace the placeholder's 'image'
                placeholder.image = photo  
                self.setup_label_bindings(placeholder, path)
            except Exception as e:
                print(f'Error updating a thumbnail: {e}')
        scrollable_frame.after(0, _update)


    def setup_label_bindings(self, label, path):
        enter_event = partial(self.on_enter, label=label)
        leave_event = partial(self.on_leave, label=label)
        click_event = partial(self.on_thumbnail_click, path=path)

        label.bind("<Enter>", enter_event)
        label.bind("<Leave>", leave_event)
        label.bind('<Button-1>', click_event)

    def on_enter(self, event, label):
        label.config(highlightthickness=1, highlightbackground="blue", highlightcolor="blue")

    def on_leave(self, event, label):
        label.config(highlightthickness=0)

    def on_thumbnail_click(self, event, path):
        print(f"Thumbnail clicked: {path}")

    def find_image_paths(self):
        try:
            base_directory = "ocr_results"
            unique_id = self.current_unique_id
            image_paths = []
            unique_id_directory = os.path.join(base_directory, unique_id)
            if os.path.exists(unique_id_directory) and os.path.isdir(unique_id_directory):
                for filename in os.listdir(unique_id_directory):
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                        file_path = os.path.join(unique_id_directory, filename)
                        image_paths.append(file_path)
            return image_paths
        except Exception as e:
            print(f'There was an error finding associated image paths: {e}')
            return []

    def create_label_control_frame(self, parent):
        control_frame = ctk.CTkFrame(parent, width=200, fg_color="transparent")
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=0, pady=(10,0))
        control_frame.pack_propagate(0)

        progress_bar = ctk.CTkProgressBar(control_frame, orientation="horizontal")
        progress_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        progress_value = 0.15
        progress_bar.set(progress_value)
        nav_frame = ctk.CTkFrame(control_frame)
        nav_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        prev_btn = ctk.CTkButton(nav_frame, text="<< Previous", command=self.prev_page)
        prev_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.page_count_label = ctk.CTkLabel(nav_frame, text=f"Page {self.current_page + 1} of {self.total_pages}")
        self.page_count_label.pack(side=tk.LEFT, expand=True, padx=10)
        next_btn = ctk.CTkButton(nav_frame, text="Next >>", command=self.next_page)
        next_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.switch_var = tk.StringVar(value="on")
        self.switch = ctk.CTkSwitch(master=control_frame, variable=self.switch_var, text="Labels", command=self.toggle_zone_labels, onvalue="on", offvalue="off")
        self.switch.grid(row=2, column=0, sticky="e", padx=10, pady=(10,0))

        tab_view = ctk.CTkTabview(master=parent)
        tab_view.pack(expand=True, fill="both", padx=5)

        labels_tab = tab_view.add("Labels")  
        json_data_tab = tab_view.add("JSON")  
        ocr_data_tab = tab_view.add("OCR Data")
        table_extraction_tab = tab_view.add("Tables")

        # json_label = ctk.CTkLabel(json_data_tab, text="JSON Content goes here") # Placeholder
        # json_label.pack(padx=0, pady=0)                                         # Placeholder

        key_value_label = ctk.CTkLabel(table_extraction_tab, text="Table Content goes here")
        key_value_label.pack(padx=0, pady=0)

        # Results Tab canvas and scrollbar
        self.results_scrollable_frame = ctk.CTkScrollableFrame(labels_tab, fg_color="white")
        self.results_scrollable_frame.pack(fill="both", expand=True)

        checkboxinfo_frame = ctk.CTkFrame(self.results_scrollable_frame)
        checkboxinfo_frame_var = ctk.StringVar(value="off")
        checkboxinfo_checkbox = ctk.CTkCheckBox(checkboxinfo_frame, text="Ignore this page", variable=checkboxinfo_frame_var, onvalue="on", offvalue="off")
        checkboxinfo_frame.pack(fill='x', expand=True, pady=0, padx=0)
        checkboxinfo_checkbox.pack(fill='x', expand=True, pady=5, padx=5)

        # for i in range(1):
        #     self.zone_info_frame = ctk.CTkFrame(results_scrollable_frame)
        #     self.zone_info_frame.pack(fill='x', expand=True, pady=5, padx=2)

        
        #JSON Tab scrollbar
        
        self.ocr_data_scrollable_frame = ctk.CTkScrollableFrame(ocr_data_tab, fg_color="white")
        self.ocr_data_scrollable_frame.pack(fill="both", expand=True)

        # zone_scroll_frame = tk.Frame(labels_tab) 
        # zone_scroll_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        # labels_tab.grid_columnconfigure(0, weight=1) 
        # labels_tab.grid_rowconfigure(0, weight=1)  
        # self.zone_canvas = tk.Canvas(zone_scroll_frame)
        # self.zone_canvas.pack(side="left", fill="both", expand=True)
        # scrollbar = ctk.CTkScrollbar(zone_scroll_frame, orientation="vertical", command=self.zone_canvas.yview)
        # scrollbar.pack(side="right", fill="y")
        # self.zone_canvas.config(yscrollcommand=scrollbar.set)
        # self.zone_info_frame = ctk.CTkFrame(self.zone_canvas)
        # self.zone_canvas.create_window((0, 0), window=self.zone_info_frame, anchor="nw", width=self.zone_canvas.cget('width'))
        # self.zone_canvas.bind("<MouseWheel>", self.scroll_zone_canvas)
        # self.zone_info_frame.bind("<MouseWheel>", self.scroll_zone_canvas)
        # self.zone_info_frame.bind("<Configure>", lambda e: self.zone_canvas.configure(scrollregion=self.zone_canvas.bbox("all")))

        # OCR Data Tab canvas and scrollbar setup
        self.json_scrollable_frame = ctk.CTkScrollableFrame(json_data_tab, fg_color="white")
        self.json_scrollable_frame.pack(fill="both", expand=True)
        # for i in range(10):
        #     tets_ocr_data_zone_info_frame = ctk.CTkFrame(self.json_scrollable_frame)
        #     tets_ocr_data_zone_info_frame.pack(fill='x', expand=True, pady=2, padx=2)
        #     example_label = ctk.CTkLabel(tets_ocr_data_zone_info_frame, text=f" {i}. Example content inside scrollable frame.")
        #     example_label.pack(fill='x', expand=True, pady=10, padx=10)



    def scroll_zone_canvas(self, event):
        self.zone_canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    def toggle_zone_labels(self):
        print(self.switch_var.get())
        if self.switch_var.get() == "on":
            state = tk.NORMAL
        else:
            state = tk.HIDDEN
        for zone in self.zones_info:
            if 'label' in zone and zone['label']:
                self.canvas.itemconfigure(zone['label'], state=state)

    def update_template_dropdown(self):
        templates = self.get_template_names()
        self.template_var.set('Select Template' if templates else 'No Templates')
        menu = self.template_dropdown['menu']
        menu.delete(0, 'end')
        for template in templates:
            display_name = template.replace('.json', '')
            menu.add_command(label=display_name, command=lambda value=template: self.template_var.set(value))

    def load_selected_template(self):
        selected_template = self.template_var.get()
        if selected_template in ['Select Template', 'No Templates']:
            print("No template selected.")
            return

        self.clear_zones()

        template_path = os.path.join(self.templates_dir, selected_template)
        with open(template_path, 'r') as file:
            template_data = json.load(file)
        self.apply_template(template_data)

    def adjust_zones_to_canvas_size(self):
        try:
            for zone in self.zones_info:
                original_coords = zone['original_coordinates']
                new_coords = []
                for i in range(0, len(original_coords), 2):
                    scaled_x = (original_coords[i] * self.zoom_factor) + self.img_offset_x
                    new_coords.append(scaled_x)

                    scaled_y = (original_coords[i + 1] * self.zoom_factor) + self.img_offset_y
                    new_coords.append(scaled_y)
                self.canvas.coords(zone['rect'], *new_coords)
        except Exception as e:
            print(f'Error adjusting zones to canvas size: {e}')

    
    def display_page(self):
        self.update_page_count_label()
        self.update()
        if not hasattr(self, 'png_files') or self.current_page < 0 or self.current_page >= self.total_pages:
            print("No document loaded or invalid page number.")
            return
        png_file_path = self.png_files[self.current_page]
        self.load_json_data(png_file_path, self.current_page, self.current_unique_id)
        try:
            img = Image.open(png_file_path)
            canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
            control_frame_buffer = 75   # Buffer space for the control frame (adjust as needed)
            # Calculate zoom factor based on width and height (without buffer space)
            width_zoom = canvas_width / img.width
            height_zoom = canvas_height / img.height
            zoom_factor = min(width_zoom, height_zoom, 1)
            img_resized = img.resize((int(img.width * zoom_factor), int(img.height * zoom_factor)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_resized)
            # Calculate centered position
            x = (canvas_width - img_resized.width) / 2
            y = (canvas_height - img_resized.height) / 2
            self.update_image_adjustments(img.width, img.height, canvas_width, canvas_height, zoom_factor, x, y)
            if hasattr(self, 'canvas_image_id'): # Update or create the image on the canvas at the centered position
                self.canvas.itemconfig(self.canvas_image_id, image=photo)
                self.canvas.coords(self.canvas_image_id, x, y)
            else:
                self.canvas_image_id = self.canvas.create_image(x, y, image=photo, anchor=tk.NW)

            self.canvas.image = photo  # Keep a reference
            self.adjust_zones_to_canvas_size()
            self.status_bar.config(text=f"Page {self.current_page + 1} of {self.total_pages}")
            self.update_canvas_scale()  
            self.clear_ocr_bounding_boxes()
            if self.show_saved_ocr_zones() and self.current_json_data:
                self.display_ocr_zones()
            self.load_json_data_into_scrollable_frame_tab()
        except Exception as e:
            print(f"Failed to load or display page image: {e}")

    def update_image_adjustments(self, original_img_width, original_img_height, canvas_width, canvas_height, zoom_factor, img_x, img_y):
        ''' Store the calculated zoom factor and image offset values '''
        ''' especially used for draw_bbox_on_canvas, extract_text_from_zone, adjust_zones_to_canvas_size, display_ocr_zones, adjust_zones_to_canvas_size'''
        self.zoom_factor = zoom_factor
        self.img_offset_x = img_x
        self.img_offset_y = img_y

    def display_ocr_zones(self):
        for item in self.current_json_data:
            bbox = item.get('bbox', [])
            if bbox:
                self.draw_bbox_on_canvas(bbox)


    def update_canvas_scale(self):  
        try:
            if hasattr(self, 'canvas_image'):
                img_width = self.canvas_image.width()
                img_height = self.canvas_image.height()
                canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
                self.canvas_scale = min(canvas_width / img_width, canvas_height / img_height)
        except Exception as e:
            print(f'Error in canvas scale: {e}')


    def load_json_data_into_scrollable_frame_tab(self):
        for widget in self.ocr_data_scrollable_frame.winfo_children():
            widget.destroy()
        if hasattr(self, 'current_json_data') and self.current_json_data:
            formatted_text = json.dumps(self.current_json_data, indent=4)
            label = ctk.CTkLabel(self.ocr_data_scrollable_frame, text=formatted_text, justify=tk.LEFT, wraplength=300)
            label.pack(pady=2, padx=5, anchor='w')
                
                
    def draw_bbox_on_canvas(self, bbox):
        x_min, y_min, x_max, y_max = bbox
        scaled_x_min = x_min * self.zoom_factor + self.img_offset_x
        scaled_y_min = y_min * self.zoom_factor + self.img_offset_y
        scaled_x_max = x_max * self.zoom_factor + self.img_offset_x
        scaled_y_max = y_max * self.zoom_factor + self.img_offset_y
        self.canvas.create_rectangle(scaled_x_min, scaled_y_min, scaled_x_max, scaled_y_max, outline="red", tags="debug-bbox")


    def clear_ocr_bounding_boxes(self): # display OCRd zones for debugging
        try:
            self.canvas.delete("debug-bbox")
        except Exception as e:
            print(f'error clearing ocr bounding boxes: {e}')

    def update_page_count_label(self):
        self.page_count_label.configure(text=f"Page {self.current_page + 1} of {self.total_pages}")

    def show_saved_ocr_zones(self):
        env_value = os.getenv('Show_Json_Saved_OCR_Zones', 'False')
        return env_value.lower() == 'true'

    def select_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if file_path:
            self.pdf_document = fitz.open(file_path)
            self.total_pages = len(self.pdf_document)
            self.get_page_sizes()
            self.current_page = 0
            self.display_page()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.clear_zones()
            self.update_page_count_label()
            self.display_page()

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.clear_zones()
            self.update_page_count_label()
            self.display_page()

    def get_page_sizes(self):
        self.page_sizes = [page.rect.br - page.rect.tl for page in self.pdf_document]

    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_canvas_click(self, event):
        clicked_inside_zone = False
        for zone in self.zones_info:
            if self.is_point_in_zone(event.x, event.y, zone):
                clicked_inside_zone = True
                self.show_tooltip_for_selected_zone(zone)
                break  # Stop checking other zones as we found the clicked one
        if not clicked_inside_zone and hasattr(self, 'tooltip') and self.tooltip.winfo_exists():
            self.tooltip.hide_tooltip()
        if not clicked_inside_zone:
            if self.rect:
                self.canvas.delete(self.rect)  # Delete the prezone if it exists
            self.start_x = self.canvas.canvasx(event.x)
            self.start_y = self.canvas.canvasy(event.y)
            self.rect = self.canvas.create_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y,
                outline=self.get_unique_color(), width=2, dash=(4, 2)
            )

    def on_canvas_drag(self, event):
        cur_x, cur_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_canvas_release(self, event):
        if self.ignore_next_release:
            self.ignore_next_release = False
            return
        self.end_x, self.end_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        box_width = abs(self.start_x - self.end_x)
        box_height = abs(self.start_y - self.end_y)
        if self.rect and (box_width < 5 and box_height < 5):
            self.canvas.delete(self.rect)
            return
        if box_width >= 5 and box_height >= 5:
            zone_created = True
            for zone in self.zones_info:
                if self.is_point_in_zone(self.end_x, self.end_y, zone):
                    zone_created = False
                    break 
            if zone_created:
                zone_coords = (self.start_x, self.start_y, self.end_x, self.end_y)
                self.add_zone_field(coordinates=zone_coords) 
                self.extract_text_from_zone(zone_coords)
        if self.rect:
            self.canvas.delete(self.rect)  # Remove temporary drawn rectangle
            self.rect = None

    def is_point_in_zone(self, x, y, zone):
        x1, y1, x2, y2 = self.canvas.coords(zone['rect'])
        return (x1 <= x <= x2) and (y1 <= y <= y2)

    def extract_text_from_zone(self, zone_coords):
        if not self.current_json_data:
            print("No OCR data loaded for this document.")
            return
        if not hasattr(self, 'current_unique_id'):
            print("No document unique ID available.")
            return
        doc_info = next((doc for doc in self.document_database if doc['unique_id'] == self.current_unique_id), None)
        if not doc_info or 'dimensions' not in doc_info:
            print("Original dimensions not found for the current document.")
            return
        dimensions_str = doc_info['dimensions'].strip('[]')
        original_width, original_height = map(int, dimensions_str.split(','))
        # Adjust the zone coordinates using the inverse of the zoom factor and accounting for image offsets
        inv_scale_x, inv_scale_y = 1 / self.zoom_factor, 1 / self.zoom_factor
        scaled_x1 = (zone_coords[0] - self.img_offset_x) * inv_scale_x
        scaled_y1 = (zone_coords[1] - self.img_offset_y) * inv_scale_y
        scaled_x2 = (zone_coords[2] - self.img_offset_x) * inv_scale_x
        scaled_y2 = (zone_coords[3] - self.img_offset_y) * inv_scale_y
        print("Original Zone Coordinates:", zone_coords)
        print("Scaled Zone Coordinates:", scaled_x1, scaled_y1, scaled_x2, scaled_y2)
        zone_texts = []
        for item in self.current_json_data:
            word_bbox = item.get('bbox', [])
            if self.is_bbox_in_zone(word_bbox, scaled_x1, scaled_y1, scaled_x2, scaled_y2):
                zone_texts.append(item.get('text', ''))
        print("Texts in the zone:", " ".join(zone_texts))

    def convert_bbox_to_dict(self, bbox):
        return {'vertices': [{'x': point[0], 'y': point[1]} for point in bbox]}

    def is_bbox_in_zone(self, bbox, x1, y1, x2, y2):
        # bbox format: [x_min, y_min, x_max, y_max]
        bbox_x1, bbox_y1, bbox_x2, bbox_y2 = bbox
        bbox_area = abs((bbox_x2 - bbox_x1) * (bbox_y2 - bbox_y1))
        overlap_x1 = max(x1, bbox_x1)
        overlap_y1 = max(y1, bbox_y1)
        overlap_x2 = min(x2, bbox_x2)
        overlap_y2 = min(y2, bbox_y2)
        if overlap_x2 > overlap_x1 and overlap_y2 > overlap_y1:
            overlap_area = (overlap_x2 - overlap_x1) * (overlap_y2 - overlap_y1)
        else:
            overlap_area = 0
        return overlap_area >= float(os.getenv('zone_overlap', 0.35)) * bbox_area



    def on_canvas_resize(self, event):
        self.display_page()

    def update_zone_positions(self):
        if not self.pdf_document or self.original_pdf_page_size == (0, 0):
            return
        if not self.pdf_document or self.current_page >= self.total_pages:
            return
        current_page_size = self.page_sizes[self.current_page]
        canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        scale_x = canvas_width / current_page_size.width
        scale_y = canvas_height / current_page_size.height
        for zone in self.zones_info:
            if 'original_coordinates' in zone and zone['original_coordinates']:
                orig_coords = zone['original_coordinates']
                new_coords = [
                    orig_coords[0] * scale_x, orig_coords[1] * scale_y,
                    orig_coords[2] * scale_x, orig_coords[3] * scale_y
                ]
                self.canvas.coords(zone['rect'], *new_coords)

    def update_zone_label(self, zone, event=None):
        new_text = zone['entry'].get()
        self.canvas.itemconfigure(zone['label'], text=new_text)

    def add_zone_field(self, zone_name=None, coordinates=None):
        canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        label_x = coordinates[0] - 0  # X coordinate for the label (0 pixels to the left of the rectangle's left edge)
        label_y = coordinates[1] - 18  # Y coordinate for the label (18 pixels above the rectangle's top edge)

        label_x = max(label_x, 0)
        label_y = max(label_y, 0)
        rect_id = self.canvas.create_rectangle(*coordinates, fill='', width=2)
        label_id = self.canvas.create_text(label_x, label_y, text=zone_name, anchor='nw')
        zone = {
            'rect': rect_id,
            'original_coordinates': coordinates,
            'label': label_id,
            'selected': False,
        }
        self.zones_info.append(zone)
        if self.rect:
            self.canvas.delete(self.rect)
            self.rect = None
        zone['selected'] = False
        self.canvas.tag_bind(rect_id, "<Button-1>", lambda event, z=zone: self.on_zone_click(event, z))
        # zone_entry.bind("<KeyRelease>", lambda event, z=zone: self.update_zone_label(z, event))



    def on_zone_click(self, event, zone):
        self.show_tooltip_for_selected_zone(zone)
        
    def show_tooltip_for_selected_zone(self, zone):
        def save_zone_callback(zone_info):
            print(f"Zone saved with label: {zone_info['label']}")
            #push data to JSON Tab
            zone['label'] = zone_info['label']
            self.save_zone_data_to_json_tab()
            new_color = self.find_color_for_label(zone_info['label'])
            print('new color:', new_color)
            if new_color:
                self.change_zone_color(zone['rect'], new_color)


        def delete_zone_callback(zone_info):
            self.delete_drawn_zone(zone_info['rect'])

        existing_label_names = model_label_names
        box_width = abs(zone['original_coordinates'][0] - zone['original_coordinates'][2])
        box_height = abs(zone['original_coordinates'][1] - zone['original_coordinates'][3])
        self.tooltip = Tooltip(self, zone, save_zone_callback, delete_zone_callback, existing_label_names)
        self.tooltip.show_tooltip(self.canvas, zone['original_coordinates'][0], zone['original_coordinates'][1], box_width, box_height)

    def delete_drawn_zone(self, rect_id):
        zone_index = next((i for i, zone in enumerate(self.zones_info) if zone['rect'] == rect_id), None)
        if zone_index is not None:
            zone = self.zones_info.pop(zone_index)
            print(f"Deleting zone: {zone_index}")
            self.canvas.delete(zone['rect'])  
            if 'label' in zone:
                self.canvas.delete(zone['label'])  # Delete the label from the canvas if it exists
            
            if self.rect:
                self.canvas.delete(self.rect)
                self.rect = None
            self.canvas.update()
        else:
            print("No matching zone found to delete.")


    def save_zone_data_to_json_tab(self):
            saved_zones = []
            for zone in self.zones_info:
                zone_data = {
                    "label": zone['label'],
                    "ocr_text": zone.get('ocr_text', ''),
                    "confidence": zone.get('confidence'), 
                    "bbox": zone['original_coordinates'],
                }
                saved_zones.append(zone_data)
            self.display_saved_zones(saved_zones)

    def display_saved_zones(self, saved_zones):
        for widget in self.json_scrollable_frame.winfo_children():
            widget.destroy()
        for i, zone_data in enumerate(saved_zones):
            formatted_text = json.dumps(zone_data, indent=4)
            label = ctk.CTkLabel(self.json_scrollable_frame, text=formatted_text, justify=tk.LEFT, wraplength=300)
            label.pack(anchor='w', expand=True, pady=2, padx=5)

    def delete_zone(self, frame):
        zone_index = None
        for i, zone in enumerate(self.zones_info):
            if zone['frame'] == frame:
                zone_index = i
                break
        if zone_index is not None:
            zone = self.zones_info.pop(zone_index)
            print(f"Deleting zone: {zone_index}") 
            self.status_bar.config(text=f"Deleting zone: {zone_index}")
            self.canvas.delete(zone['rect'])
            if 'label' in zone:
                self.canvas.delete(zone['label'])
            frame.destroy()
            if self.rect:
                self.canvas.delete(self.rect)
                self.rect = None
            self.canvas.update()

    def clear_zones(self):
        for zone in list(self.zones_info):  
            self.delete_zone(zone['frame'])

    def get_unique_color(self):
        # colors = ['maroon', 'green', 'blue', 'Purple', 'magenta', 'cyan', 'black']
        colors = ['maroon', 'forestgreen', 'royalblue', 'mediumorchid', 'hotpink', 'turquoise', 'tomato', 'gold', 'limegreen', 'cornflowerblue']
        return colors[len(self.label_widgets) % len(colors)]
    

    #PaddleOCR
    def perform_ocr(self):
        save_crop_image = True
        if not self.pdf_document or not self.zones_info:
            print("No document loaded or zones defined.")
            return
        cropped_images_dir = "cropped_images"
        if not os.path.exists(cropped_images_dir):
            os.makedirs(cropped_images_dir)
        image_count = 1
        for zone in self.zones_info:
            if zone['rect']:
                coords = self.canvas.coords(zone['rect'])
                scaled_coords = [c * self.canvas_scale for c in coords]
                if self.ocr_engine == 'PaddleOCR':
                    ocr_output_text = self.perform_paddleocr_on_coordinates(scaled_coords)
                elif self.ocr_engine == 'Google Vision':
                    ocr_output_text = self.perform_google_vision_on_coordinates(scaled_coords)

                if save_crop_image:
                    cropped_image = self.crop_image(*coords)
                    cropped_image.save(os.path.join(cropped_images_dir, f"cropped_{image_count}.png"))
                image_count += 1
                zone['ocr_output'].delete(1.0, tk.END)
                zone['ocr_output'].insert(tk.END, ocr_output_text)
                print(f"{zone['entry'].get()}: {ocr_output_text}")
        self.save_ocr_output_to_json()

    def save_ocr_output_to_json(self, base_name, ocr_results):
        target_directory = os.path.join("ocr_results", base_name)
        for page_num, results in ocr_results.items():
            print('page num::', page_num)
            json_filename = f"{base_name}_page_{page_num}.json"
            json_path = os.path.join(target_directory, json_filename)
            with open(json_path, 'w') as outfile:
                json.dump(results, outfile, indent=4)

    def perform_paddleocr_on_image(self, cv_image):
        try:
            if not hasattr(np, 'int'):
                np.int = int

            ocr_result = self.ocr.ocr(cv_image)
            detailed_ocr_results = []
            for line in ocr_result:
                original_bbox = line[0]
                text, confidence = line[1]
                converted_bbox = self.convert_bbox_format(original_bbox)
                detailed_ocr_results.append({
                    'text': text,
                    'bbox': converted_bbox,
                })
            return detailed_ocr_results
        except Exception as e:
            print(f"Error during PaddleOCR Image processing: {e}")
            return []




    def convert_bbox_format(self, bbox):
        x_coordinates = [point[0] for point in bbox]
        y_coordinates = [point[1] for point in bbox]
        x_min = min(x_coordinates)
        y_min = min(y_coordinates)
        x_max = max(x_coordinates)
        y_max = max(y_coordinates)
        return [x_min, y_min, x_max, y_max]

    def perform_google_vision_on_coordinates(self, coordinates):
        if not self.google_vision_client:
            self.initialize_google_vision()
        x1, y1, x2, y2 = coordinates
        cropped_image = self.crop_image(x1, y1, x2, y2)
        image_bytes = io.BytesIO()
        cropped_image.save(image_bytes, format='PNG')
        content = image_bytes.getvalue()
        image = vision.Image(content=content)
        response = self.google_vision_client.document_text_detection(image=image)
        return response.full_text_annotation

    def crop_image(self, x1, y1, x2, y2):
        page = self.pdf_document.load_page(self.current_page)
        page_size = page.rect.br - page.rect.tl
        window_width, window_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        zoom_factor = min(window_width / page_size.x, window_height / page_size.y)
        adj_x1, adj_y1 = x1 / zoom_factor, y1 / zoom_factor
        adj_x2, adj_y2 = x2 / zoom_factor, y2 / zoom_factor
        pix = page.get_pixmap()
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return image.crop((adj_x1, adj_y1, adj_x2, adj_y2))

    def find_color_for_label(self, label_name):
        for label_info in self.label_widgets:
            if label_info['label_name'].cget("text") == label_name + ":":  # Adjust based on how label_name is stored
                return label_info['color']
        return None
    
    def change_zone_color(self, rect_id, new_color):
        self.canvas.itemconfig(rect_id, outline=new_color)


class Tooltip(ctk.CTkToplevel):
    def __init__(self, parent, zone_info, on_save, on_delete, existing_zone_names):
        super().__init__(parent)
        self.wm_overrideredirect(True)
        self.zone_info = zone_info
        self.on_save = on_save
        self.on_delete = on_delete
        self.existing_zone_names = existing_zone_names
        self.init_ui()

    def init_ui(self):
        # OCR Text Label
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(padx=10, pady=10, fill='both', expand=True)
        ocr_text_title_label = ctk.CTkLabel(main_frame, text="Text")
        ocr_text_title_label.pack(padx=5, pady=(0, 0))
        separator = ttk.Separator(main_frame, orient='horizontal')
        separator.pack(fill='x', expand=True)
        ocr_text_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=100)
        ocr_text_frame.pack(padx=5, pady=5, fill='both', expand=True)
        ocr_text_content = ctk.CTkTextbox(master=ocr_text_frame, fg_color="white", activate_scrollbars=False, wrap="word", height=100)
        ocr_text_content.insert("0.0", "Some example text!\n")
        ocr_text_content.pack(padx=0, pady=0, fill='both', expand=True)

        self.label_var = tk.StringVar(value="Label")
        label_dropdown = ctk.CTkOptionMenu(master=self, variable=self.label_var, values=self.existing_zone_names)
        label_dropdown.pack(padx=10, pady=5)

        btn_frame = tk.Frame(self, bg="#f0f0f0")
        btn_frame.pack(pady=5, fill='x')

        delete_btn = ctk.CTkButton(btn_frame, text="Delete", command=self.delete_zone, width=100, fg_color="maroon")
        delete_btn.pack(side=tk.LEFT, padx=10, pady=10, expand=True)

        save_btn = ctk.CTkButton(btn_frame, text="Save", command=self.save_zone, width=100)
        save_btn.pack(side=tk.LEFT, padx=10, pady=10, expand=True)

    def show_tooltip(self, canvas, x, y, width, height):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        abs_x = canvas.winfo_rootx() + x
        abs_y = canvas.winfo_rooty() + y
        offset_x = width // 2  # Center the tooltip
        offset_y = height // 2  # Position it below the box

        abs_x = int(abs_x + offset_x)
        abs_y = int(abs_y + offset_y)

        if abs_x + self.winfo_reqwidth() > screen_width:
            abs_x = abs_x - self.winfo_reqwidth() - width

        if abs_y + self.winfo_reqheight() > screen_height:
            abs_y = abs_y - self.winfo_reqheight() - height

        self.geometry(f"+{abs_x}+{abs_y}")
        self.deiconify()

    def hide_tooltip(self):
        self.withdraw()

    def save_zone(self):
        selected_label = self.label_var.get()  
        self.zone_info['label'] = selected_label
        self.on_save(self.zone_info)
        self.destroy()
        self.master.ignore_next_release = True

    def delete_zone(self, event=None):
        self.on_delete(self.zone_info)
        self.destroy()
        self.master.ignore_next_release = True



if __name__ == "__main__":
    app = KeyValueModelBuilder()
    app.mainloop()