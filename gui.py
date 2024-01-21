import sqlite3
import os
import re

import json
import tkinter as tk
from tkinter import Menu, filedialog, Frame, Canvas, Scrollbar, Label, Entry, Button, simpledialog, PhotoImage, ttk
import fitz
from PIL import Image, ImageTk
import pytesseract
from PIL import ImageOps
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
from dotenv import load_dotenv

pytesseract.pytesseract.tesseract_cmd = r'.\tesseract_bin\tesseract.exe'
load_dotenv()

class KeyValueModelBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Key-Value Model Builder")
        self.geometry("1200x850")
        self.pdf_document = None
        self.current_page = 0
        self.total_pages = 0
        self.start_x, self.start_y = None, None
        self.rect = None
        self.show_zone_labels = True  # Add this line to control the visibility of labels names on zonal boxes
        self.templates_dir = "templates"
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir)
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
        self.populate_treeview_with_database()
        self.update_folder_sizes()
        self.apply_alternating_row_colors()
        self.initialize_ocr_engine()

    def init_ui(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(expand=True, fill='both')
        
        self.notebook = ttk.Notebook(main_frame)
        self.document_files_list = ctk.CTkFrame(self.notebook)
        self.notebook.add(self.document_files_list, text='Document Files')
        self.document_viewer = ctk.CTkFrame(self.notebook)
        # self.notebook.add(self.document_viewer, text='File Viewer')

        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.create_document_viewer(self.document_files_list)
        self.create_canvas(self.document_viewer)
        self.create_control_frame(self.document_viewer)
        self.create_menu_bar()
        self.create_status_bar(main_frame)

        main_frame.grid_rowconfigure(0, weight=1)  # Give notebook most of the space
        main_frame.grid_rowconfigure(1, weight=0)  # Status bar 
        main_frame.grid_columnconfigure(0, weight=1)

        self.ocr_engine = os.getenv('OCR_Engine', 'PaddleOCR')

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
            rows = cursor.fetchall()
            conn.close()

            document_database = []
            for row in rows:
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
        

    def insert_document(self, document):
        conn = sqlite3.connect('document_database.sqlite')
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO documents
                    (file_name, upload_date, progress, filetype, page_count, status, size, dimensions, unique_id, file_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                    (document['file_name'], document['upload_date'], document['progress'], document['filetype'], document['page_count'], document['status'], document['size'], str(document['dimensions']), document['unique_id'], document['file_path']))
        conn.commit()
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


    def create_document_viewer(self, parent):
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
        self.document_list.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.context_menu = tk.Menu(self.document_list, tearoff=0)
        self.context_menu.add_command(label="Scan Document", command=self.scan_document)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete Upload", command=self.delete_document)
        
        self.document_list.bind("<Button-3>", self.show_context_menu)
        self.document_list.bind("<<TreeviewSelect>>", self.on_treeview_select)
        self.document_list.bind("<Double-1>", self.open_document)
        self.document_list.bind("<Configure>", self.adjust_columns)
        self.adjust_columns()

        button_frame = tk.Frame(parent)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X)
        import_btn = ctk.CTkButton(button_frame, text="Import Document(s)", command=self.add_document)
        import_btn.pack(side=tk.LEFT, padx=5, pady=5)
        scan_btn = ctk.CTkButton(button_frame, text="Scan Document", command=self.scan_document)
        scan_btn.pack(side=tk.LEFT, padx=5, pady=5)

        # Variable to store the selected model
        self.selected_model = tk.StringVar(parent)
        self.model_option_menu = ctk.CTkOptionMenu(master=button_frame, variable=self.selected_model, values=self.get_model_names())
        self.model_option_menu.pack(side=tk.RIGHT, padx=5, pady=5)
        self.selected_model.set('Select Model')
        # Optionally, you can add a trace to the variable to handle changes
        self.selected_model.trace("w", self.on_model_selected)

    def get_model_names(self):
        return ['model1', 'model2']
    
    def on_model_selected(self, *args):
            selected_model = self.selected_model.get()
            print(f"Model selected: {selected_model}")

    def show_file_viewer_tab(self):
        """dd the 'File Viewer' tab to the notebook."""
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
                except Exception as e:
                    print(f"There was an exception: {e}")
                    self.update_document_data(unique_id, status="New")
                else:
                    print(f"Scan document - Target directory not found for {file_name}")
            try:
                ocr_thread = threading.Thread(target=start_ocr_process)
                ocr_thread.start()
            except Exception as e:
                    print(f"There was an exception during threading: {e}")
                    self.update_document_data(unique_id, status="New")
        else:
            print("No document selected")
            

    def delete_document_from_database(self, unique_id):
        conn = sqlite3.connect('document_database.sqlite')
        cursor = conn.cursor()
        cursor.execute('''DELETE FROM documents WHERE unique_id = ?''', (unique_id,))
        conn.commit()
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

                progress = (page_num) / total_pages * 100
                self.update_folder_sizes()
                self.update_document_data(unique_id, progress=progress, dimensions=original_dimensions)
                if progress == 100:
                    self.update_document_data(unique_id, status="To Review")
            except Exception as e:
                print(f"OCR Performance fucked up:: {e}")
                self.update_document_data(unique_id, status="New")



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
        file_menu.add_command(label="Import Document", command=self.select_pdf)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        template_menu = tk.Menu(menu_bar, tearoff=0)
        template_menu.add_command(label="Save Template", command=self.save_template)
        template_menu.add_separator()
        template_menu.add_command(label="Load Template", command=self.load_template)
        template_menu.add_separator()
        template_menu.add_command(label="New Template", command=self.new_template)

        model_menu = tk.Menu(menu_bar, tearoff=0)
        model_menu.add_command(label="New", command=self.select_pdf)

        menu_bar.add_cascade(label="File", menu=file_menu)
        menu_bar.add_cascade(label="Templates", menu=template_menu)
        menu_bar.add_cascade(label="Model", menu=model_menu)
        self.config(menu=menu_bar)
    
    def new_template(self):
        self.clear_zones()

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
        self.canvas.pack(side=tk.LEFT, fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

    def create_control_frame(self, parent):
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
        tab_view.pack(expand=True, fill="both", padx=5, pady=(0 ,20))

        labels_tab = tab_view.add("Labels")  
        json_data_tab = tab_view.add("JSON")  
        ocr_data_tab = tab_view.add("OCR Data")
        key_value_tab = tab_view.add("Kay-Value")

        json_label = ctk.CTkLabel(json_data_tab, text="JSON Content goes here")
        json_label.pack(padx=0, pady=0)

        key_value_label = ctk.CTkLabel(key_value_tab, text="Key-Value Content goes here")
        key_value_label.pack(padx=0, pady=0)

        # Results Tab canvas and scrollbar
        self.results_scrollable_frame = ctk.CTkScrollableFrame(labels_tab, fg_color="white")
        self.results_scrollable_frame.pack(fill="both", expand=True)

        checkboxinfo_frame = ctk.CTkFrame(self.results_scrollable_frame)
        checkboxinfo_frame_var = ctk.StringVar(value="off")
        checkboxinfo_checkbox = ctk.CTkCheckBox(checkboxinfo_frame, text="This is a static checkbox", variable=checkboxinfo_frame_var, onvalue="on", offvalue="off")
        checkboxinfo_frame.pack(fill='x', expand=True, pady=0, padx=0)
        checkboxinfo_checkbox.pack(fill='x', expand=True, pady=5, padx=5)

        # for i in range(1):
        #     self.zone_info_frame = ctk.CTkFrame(results_scrollable_frame)
        #     self.zone_info_frame.pack(fill='x', expand=True, pady=5, padx=2)

        

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
        ocr_data_scrollable_frame = ctk.CTkScrollableFrame(ocr_data_tab, fg_color="white")
        ocr_data_scrollable_frame.pack(fill="both", expand=True, padx=0, pady=0)
        # self.ocr_data_zone_info_frame = ctk.CTkFrame(ocr_data_scrollable_frame)
        for i in range(10):
            tets_ocr_data_zone_info_frame = ctk.CTkFrame(ocr_data_scrollable_frame)
            tets_ocr_data_zone_info_frame.pack(fill='x', expand=True, pady=2, padx=2)
            example_label = ctk.CTkLabel(tets_ocr_data_zone_info_frame, text=f" {i}. Example content inside scrollable frame.")
            example_label.pack(fill='x', expand=True, pady=10, padx=10)
        # self.ocr_data_zone_info_frame.pack(fill="both", expand=True)



    def scroll_zone_canvas(self, event):
        self.zone_canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    def toggle_zone_labels(self):
        print(self.switch_var.get())
        if self.switch_var.get() == "on":
            state = tk.NORMAL
        else:
            state = tk.HIDDEN
        for zone in self.zones_info:
            print('getting zone info')
            print(zone)
            print(zone['label'])
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
        canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        for zone in self.zones_info:
            original_coords = zone['original_coordinates']
            if original_coords:
                new_coords = [coord * canvas_width if i % 2 == 0 else coord * canvas_height for i, coord in enumerate(original_coords)]
                self.canvas.coords(zone['rect'], *new_coords)

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

            # Buffer space for the control frame (adjust as needed)
            control_frame_buffer = 75

            # Calculate zoom factor based on width and height with buffer space
            width_zoom = (canvas_width - control_frame_buffer) / img.width
            height_zoom = canvas_height / img.height
            zoom_factor = min(width_zoom, height_zoom, 1)  # Ensure the image is not enlarged

            img_resized = img.resize((int(img.width * zoom_factor), int(img.height * zoom_factor)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img_resized)
            self.canvas.config(width=img_resized.width, height=img_resized.height)
            self.canvas.create_image(0, 0, image=photo, anchor=tk.NW)
            self.canvas.image = photo
            self.adjust_zones_to_canvas_size()
            self.status_bar.config(text=f"Page {self.current_page + 1} of {self.total_pages}")
            self.update_canvas_scale()  
            self.clear_ocr_bounding_boxes()
            if self.show_saved_ocr_zones() and self.current_json_data:
                for item in self.current_json_data: 
                    bbox = item.get('bbox', [])
                    if bbox:
                        self.draw_bbox_on_canvas(bbox, zoom_factor) 
        except Exception as e:
            print(f"Failed to load or display page image: {e}")

    def update_canvas_scale(self):  
        if hasattr(self, 'canvas_image'):
            img_width = self.canvas_image.width()
            img_height = self.canvas_image.height()
            canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
            self.canvas_scale = min(canvas_width / img_width, canvas_height / img_height)

    def draw_bbox_on_canvas(self, bbox, zoom_factor): # display OCRd zones for debugging
        x_min, y_min, x_max, y_max = bbox
        scaled_x_min, scaled_y_min = x_min * zoom_factor, y_min * zoom_factor
        scaled_x_max, scaled_y_max = x_max * zoom_factor, y_max * zoom_factor
        self.canvas.create_rectangle(scaled_x_min, scaled_y_min, scaled_x_max, scaled_y_max, outline="red", tags="debug-bbox")


    def clear_ocr_bounding_boxes(self): # display OCRd zones for debugging
        self.canvas.delete("debug-bbox")

    def update_page_count_label(self):
        self.page_count_label.configure(text=f"Page {self.current_page + 1} of {self.total_pages}")

    def show_saved_ocr_zones(self):
        env_value = os.getenv('show_saved_ocr_zones', 'False')
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
            self.canvas.delete(self.rect)  # Clean up the temporary rectangle
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
        window_width, window_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        zoom_factor = min(window_width / original_width, window_height / original_height)
        inv_scale_x, inv_scale_y = 1 / zoom_factor, 1 / zoom_factor
        scaled_x1, scaled_y1 = zone_coords[0] * inv_scale_x, zone_coords[1] * inv_scale_y
        scaled_x2, scaled_y2 = zone_coords[2] * inv_scale_x, zone_coords[3] * inv_scale_y
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
        color = self.get_unique_color()
        zone_info_frame = ctk.CTkFrame(self.results_scrollable_frame)
        zone_info_frame.pack(fill='x', expand=True, pady=5, padx=2)



        top_frame = ctk.CTkFrame(zone_info_frame, fg_color="transparent")
        top_frame.pack(side="top", fill="x", pady=5, padx=5)
        if not zone_name:
            zone_name = f"Zone_{len(self.zones_info) + 1}"
        colorLineIndicator = ctk.CTkProgressBar(master=top_frame, orientation="vertical", fg_color=color, border_color=color, progress_color=color, height=30)
        colorLineIndicator.set(1)
        colorLineIndicator.pack(side="left", padx=(0, 3), pady=0)

        zone_name_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        zone_name_frame.pack(side="left", fill="x", expand=True)
        zone_label = ctk.CTkLabel(zone_name_frame, text="Zone Name:", font=("Helvetica", 12.5))
        zone_label.pack(side="left", padx=0)

        zone_entry = ctk.CTkEntry(zone_name_frame, font=("Helvetica", 12))
        zone_entry.pack(side="left", fill="x", expand=True, padx=(0,5), pady=2)
        zone_entry.insert(0, zone_name)

            # delete_btn = ctk.CTkButton(top_frame, width=8, text="X", command=lambda: self.delete_zone(frame))
            # delete_btn.pack(side="right", padx=5)
        ocr_output_text = ctk.CTkTextbox(master=zone_info_frame, height=1.5, fg_color="#f7f7f7", font=("Helvetica", 12), wrap="word", border_color=color, border_width=1)
        ocr_output_text.pack(side="top", fill="x", padx=5, pady=2)

        zone_type_frame = ctk.CTkFrame(zone_info_frame, fg_color="transparent")
        zone_type_frame.pack(side="top", fill="x", expand=True, pady=5, padx=5)
        zone_type_label = ctk.CTkLabel(zone_type_frame, text="Type:", font=("Helvetica", 12.5))
        zone_type_label.pack(side="left", padx=5, pady=(0,1))

        field_type_var = tk.StringVar(value="Text")
        field_types = ["Text", "Number", "Date", "E-mail", "Address", "Phone Number"]
        field_type_dropdown = ctk.CTkOptionMenu(master=zone_type_frame, variable=field_type_var, values=field_types)
        field_type_dropdown.set(field_types[0])
        field_type_dropdown.pack(side="left", padx=5)

        # separator = ttk.Separator(zone_info_frame, orient='horizontal')
        # separator.pack(fill='x', expand=True, pady=(10,0))


        canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        rect_id = self.canvas.create_rectangle(*coordinates, outline=color, fill='', width=2)
        label_x = coordinates[0] - 0  # X coordinate for the label (10 pixels to the left of the rectangle's left edge)
        label_y = coordinates[1] - 18  # Y coordinate for the label (10 pixels above the rectangle's top edge)
        
        # Ensure the label does not go out of the canvas bounds
        label_x = max(label_x, 0)
        label_y = max(label_y, 0)

        label_id = self.canvas.create_text(label_x, label_y, text=zone_name, fill=color, anchor='nw')
        zone = {
            'frame': zone_info_frame,
            'entry': zone_entry,
            'field_type': field_type_var,
            'color': color,
            'rect': rect_id,
            'ocr_output': ocr_output_text,
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
        zone_entry.bind("<KeyRelease>", lambda event, z=zone: self.update_zone_label(z, event))



    def on_zone_click(self, event, zone):
        self.show_tooltip_for_selected_zone(zone)
        
    def show_tooltip_for_selected_zone(self, zone):
        def save_zone_callback(zone_info):
            print(f"Zone saved with label: {zone_info['label']}")
        def delete_zone_callback(zone_info):
            self.delete_zone(zone_info['frame'])
        existing_zone_names = [z['entry'].get() for z in self.zones_info]
        box_width = abs(zone['original_coordinates'][0] - zone['original_coordinates'][2])
        box_height = abs(zone['original_coordinates'][1] - zone['original_coordinates'][3])
        self.tooltip = Tooltip(self, zone, save_zone_callback, delete_zone_callback, existing_zone_names)
        self.tooltip.show_tooltip(self.canvas, zone['original_coordinates'][0], zone['original_coordinates'][1], box_width, box_height)

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
        colors = ['maroon', 'green', 'blue', 'Purple', 'magenta', 'cyan', 'black']
        return colors[len(self.zones_info) % len(colors)]
    

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
            ocr_result = self.ocr.ocr(cv_image)
            detailed_ocr_results = []
            for line in ocr_result:
                for element in line:
                    original_bbox, text, confidence = element[0], element[1][0], element[1][1]
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

class Tooltip(tk.Toplevel):
    def __init__(self, parent, zone_info, on_save, on_delete, existing_zone_names):
        super().__init__(parent, bg="#f0f0f0", borderwidth=1, relief="solid")
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
        ocr_text_title_label = ctk.CTkLabel(main_frame, text="Output")
        ocr_text_title_label.pack(padx=5, pady=(0, 0))
        separator = ttk.Separator(main_frame, orient='horizontal')
        separator.pack(fill='x', expand=True)
        ocr_text_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        ocr_text_frame.pack(padx=5, pady=5, fill='both', expand=True)
        ocr_text_content = ctk.CTkTextbox(master=ocr_text_frame, fg_color="white", activate_scrollbars=False, wrap="word")
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
        abs_x = canvas.winfo_rootx() + x
        abs_y = canvas.winfo_rooty() + y
        offset_x = width // 2  # Center the tooltip
        offset_y = height // 2  # Position it below the box

        abs_x = int(abs_x + offset_x)
        abs_y = int(abs_y + offset_y)

        self.geometry(f"+{abs_x}+{abs_y}")
        self.deiconify()

    def hide_tooltip(self):
        self.withdraw()

    def save_zone(self):
        self.zone_info['label'] = self.label_var.get()
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