import os
import json
import tkinter as tk
from tkinter import Menu, filedialog, Frame, Canvas, Scrollbar, Label, Entry, Button, simpledialog, PhotoImage, ttk
import fitz
print("PyMuPDF Version:", fitz.__doc__)
from PIL import Image, ImageTk
import pytesseract
from PIL import ImageOps
import customtkinter as ctk
from paddleocr import PaddleOCR, draw_ocr
import numpy

import cv2
import numpy as np

pytesseract.pytesseract.tesseract_cmd = r'C:\Users\zach\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'




class ZonalOCRApplication(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zonal OCR Application")
        self.geometry("900x650")
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
        self.ocr = None #PaddleOCR(use_angle_cls=True, lang='en')
        self.ignore_next_release = False  # Flag to control zone creation
        
        self.zones_info = []

    def init_ui(self):
        main_frame = tk.Frame(self)
        main_frame.pack(expand=True, fill='both')
        
        self.notebook = ttk.Notebook(main_frame)
        self.ocr_tab = tk.Frame(self.notebook)
        self.notebook.add(self.ocr_tab, text='OCR Zone Creation')
        self.document_viewer_tab = tk.Frame(self.notebook)
        self.notebook.add(self.document_viewer_tab, text='Document Files')

        # Using grid for layout management within the main frame.
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.create_document_viewer(self.document_viewer_tab)
        self.create_canvas(self.ocr_tab)
        self.create_control_frame(self.ocr_tab)
        self.create_menu_bar()
        self.create_status_bar(main_frame)

        # Configure the main frame's grid
        main_frame.grid_rowconfigure(0, weight=1)  # Give notebook most of the space
        main_frame.grid_rowconfigure(1, weight=0)  # Status bar takes minimum space needed
        main_frame.grid_columnconfigure(0, weight=1)

    def create_document_viewer(self, parent):
        self.document_canvas = tk.Canvas(parent, bg='white', cursor="arrow")
        self.document_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def create_menu_bar(self):
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Load PDF", command=self.select_pdf)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        template_menu = tk.Menu(menu_bar, tearoff=0)
        template_menu.add_command(label="Save Template", command=self.save_template)
        template_menu.add_separator()
        template_menu.add_command(label="Load Template", command=self.load_template)
        template_menu.add_separator()
        template_menu.add_command(label="New Template", command=self.new_template)
        menu_bar.add_cascade(label="File", menu=file_menu)
        menu_bar.add_cascade(label="Templates", menu=template_menu)
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
        ttk.OptionMenu(select_window, selected_template, *template_names).pack()
        load_button = ctk.CTkButton(select_window, text="Load Template",
                                command=lambda: self.apply_selected_template(selected_template.get(), select_window))
        load_button.pack()

    def apply_template(self, template_data):
        if not self.pdf_document or self.current_page >= self.total_pages:
            print("No PDF document loaded or invalid page number.")
            return
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
        control_frame = ctk.CTkFrame(parent, width=200)
        control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        control_frame.pack_propagate(0)
        btn = ctk.CTkButton(control_frame, text="Select a PDF", command=self.select_pdf)
        btn.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        ocr_btn = ctk.CTkButton(control_frame, text="Perform OCR", command=self.perform_ocr)
        ocr_btn.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        # toggle_labels_btn = ctk.CTkButton(control_frame, text="Toggle Labels", command=self.toggle_zone_labels)
        # toggle_labels_btn.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        # self.page_count_label = tk.Label(control_frame, text="Page: 0 of 0") # remove comment to view page numbers under zone labels
        # self.page_count_label.grid(row=9, column=0, sticky="ew", padx=10, pady=10) # remove comment to view page numbers under zone labels
        # add_zone_btn = ctk.CTkButton(control_frame, text="Add Zone", command=self.add_zone_field)
        # add_zone_btn.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
        self.template_var = tk.StringVar(self)
        self.template_dropdown = ttk.OptionMenu(control_frame, self.template_var, '')
        self.template_dropdown.grid(row=4, column=0, sticky="ew", padx=10, pady=10)
        self.update_template_dropdown()
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', font=('Helvetica', 10), borderwidth=0, focuscolor=style.configure(".")["background"])
        style.configure('TEntry', font=('Helvetica', 10), borderwidth=0)
        load_template_btn = ctk.CTkButton(control_frame, text="Load Template", command=self.load_selected_template)
        load_template_btn.grid(row=5, column=0, sticky="ew", padx=10, pady=10)
        nav_frame = tk.Frame(control_frame)
        nav_frame.grid(row=6, column=0, sticky="ew", padx=10, pady=10)
        prev_btn = ctk.CTkButton(nav_frame, text="<< Previous", command=self.prev_page)
        prev_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
        next_btn = ctk.CTkButton(nav_frame, text="Next >>", command=self.next_page)
        next_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.is_on = True
        self.on_image = PhotoImage(file="static\on.png").subsample(2, 2)
        self.off_image = PhotoImage(file="static\off.png").subsample(2, 2)
        self.toggle_switch = Button(control_frame, image=self.on_image, bd=0, command=self.toggle_zone_labels)
        self.toggle_switch.grid(row=7, column=0, sticky="e", padx=20, pady=10)
        zone_scroll_frame = tk.Frame(control_frame)
        zone_scroll_frame.grid(row=8, column=0, sticky="nsew", padx=2, pady=2)
        control_frame.grid_columnconfigure(0, weight=1)
        control_frame.grid_rowconfigure(8, weight=1)
        self.zone_canvas = tk.Canvas(zone_scroll_frame)
        self.zone_canvas.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(zone_scroll_frame, orient="vertical", command=self.zone_canvas.yview)
        scrollbar.pack(side="right", fill="y")
        self.zone_canvas.config(yscrollcommand=scrollbar.set)
        self.zone_info_frame = tk.Frame(self.zone_canvas)
        self.zone_canvas.create_window((0, 0), window=self.zone_info_frame, anchor="nw", width=self.zone_canvas.cget('width'))
        self.zone_canvas.bind("<MouseWheel>", self.scroll_zone_canvas)
        self.zone_info_frame.bind("<MouseWheel>", self.scroll_zone_canvas)
        self.zone_info_frame.bind("<Configure>", lambda e: self.zone_canvas.configure(scrollregion=self.zone_canvas.bbox("all")))


    def create_toggle_switch(self, parent):
        self.toggle_var = tk.BooleanVar(value=False)  # Variable to hold the toggle state
        toggle_btn = tk.Checkbutton(parent, text="Toggle Labels", var=self.toggle_var,
                                    command=self.toggle_zone_labels,
                                    onvalue=True, offvalue=False,
                                    indicatoron=False,  # This removes the default checkbox style
                                    selectcolor="#80C080",
                                    bg="#F08080",  # Background color
                                    width=10)  # Width of the toggle button
        return toggle_btn


    def scroll_zone_canvas(self, event):
        self.zone_canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    # def toggle_zone_labels(self):
    #     self.show_zone_labels = not self.show_zone_labels
    #     for zone in self.zones_info:
    #         if zone['label']:
    #             self.canvas.itemconfigure(zone['label'], state=tk.NORMAL if self.show_zone_labels else tk.HIDDEN)

    def toggle_zone_labels(self):
        self.is_on = not self.is_on
        # Update the toggle switch image
        self.toggle_switch.config(image=self.on_image if self.is_on else self.off_image)
        # Update the label state
        for zone in self.zones_info:
            if 'label' in zone and zone['label']:
                self.canvas.itemconfigure(zone['label'], state=tk.NORMAL if self.is_on else tk.HIDDEN)

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
        self.update()
        if self.pdf_document and 0 <= self.current_page < self.total_pages:
            page = self.pdf_document.load_page(self.current_page)
            page_size = page.rect.br - page.rect.tl

            if self.notebook.index(self.notebook.select()) == 0:  # OCR Zone Creation tab is active
                window_width, window_height = self.canvas.winfo_width(), self.canvas.winfo_height()
            else:  # Document Viewer tab is active
                window_width, window_height = self.document_canvas.winfo_width(), self.document_canvas.winfo_height()

            zoom_factor = min(window_width / page_size.x, window_height / page_size.y)
            mat = fitz.Matrix(zoom_factor, zoom_factor)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            photo = ImageTk.PhotoImage(img)

            if self.notebook.index(self.notebook.select()) == 0:
                self.canvas.config(width=pix.width, height=pix.height)
                self.canvas.create_image(0, 0, image=photo, anchor=tk.NW)
                self.canvas.image = photo
                self.adjust_zones_to_canvas_size()
            else:
                self.document_canvas.config(width=pix.width, height=pix.height)
                self.document_canvas.create_image(0, 0, image=photo, anchor=tk.NW)
                self.document_canvas.image = photo

            self.status_bar.config(text=f"Page {self.current_page + 1} of {self.total_pages}")




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
            self.display_page()

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.clear_zones()
            self.display_page()

    def get_page_sizes(self):
        self.page_sizes = [page.rect.br - page.rect.tl for page in self.pdf_document]

    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_canvas_click(self, event):
        for zone in self.zones_info:
            if self.is_point_in_zone(event.x, event.y, zone):
                if self.rect:
                    self.canvas.delete(self.rect)  # Delete the prezone if it exists
                return  # Click is inside an existing zone; do not create a new zone
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
        box_width = abs(self.start_x - event.x)
        box_height = abs(self.start_y - event.y)
        if self.rect and (box_width < 5 and box_height < 5):
            self.canvas.delete(self.rect)
            return

        if box_width >= 5 and box_height >= 5:
            for zone in self.zones_info:
                if self.is_point_in_zone(event.x, event.y, zone):
                    self.canvas.delete(self.rect)  # Delete the prezone rectangle
                    return  # Do not create a new zone if inside an existing one
            self.add_zone_field(coordinates=(self.start_x, self.start_y, event.x, event.y))
        else:
            self.canvas.delete(self.rect)  # Delete the prezone rectangle if size criteria are not met

    def is_point_in_zone(self, x, y, zone):
        coords = self.canvas.coords(zone['rect'])
        return coords[0] <= x <= coords[2] and coords[1] <= y <= coords[3]



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
        frame = Frame(self.zone_info_frame, bg="#ffffff", bd=1, relief="flat")
        frame.pack(pady=5, padx=10, fill="x", expand=True)
        frame.bind("<MouseWheel>", self.scroll_zone_canvas)
        top_frame = Frame(frame, bg="#ffffff")
        top_frame.pack(side="top", fill="x")
        if not zone_name:
            zone_name = f"Zone_{len(self.zones_info) + 1}"
        color = self.get_unique_color()
        color_indicator = Canvas(top_frame, bg='white', width=20, height=20, bd=0, highlightthickness=0)
        color_indicator.pack(side="left", padx=5, pady=5)
        color_indicator.create_oval(2, 2, 18, 18, outline=color, fill=color)
        zone_name_frame = Frame(top_frame, bg="#ffffff")
        zone_name_frame.pack(side="left", fill="x", expand=True)
        zone_label = Label(zone_name_frame, text="Zone Name:", bg="#ffffff", font=("Helvetica", 10))
        zone_label.pack(side="left", padx=0)
        zone_entry = Entry(zone_name_frame, bd=1, relief="solid", font=("Helvetica", 10))
        zone_entry.pack(side="left", fill="x", expand=True, padx=0, pady=(0, 2))
        zone_entry.insert(0, zone_name)
        delete_btn = ctk.CTkButton(top_frame, width=8, text="X", command=lambda: self.delete_zone(frame))
        delete_btn.pack(side="right", padx=5)
        ocr_output_text = tk.Text(frame, height=1.5, bg="#f7f7f7", bd=0, font=("Helvetica", 9), wrap=tk.WORD)
        ocr_output_text.pack(side="top", fill="x", padx=5, pady=2)
        zone_type_frame = Frame(frame, bg="#ffffff")
        zone_type_frame.pack(side="top", fill="x", expand=True)
        zone_type_label = Label(zone_type_frame, text="Type:", bg="#ffffff", font=("Helvetica", 10))
        zone_type_label.pack(side="left", padx=5)
        field_type_var = tk.StringVar(value="Text")
        field_types = ["Text", "Number", "Date", "E-mail", "Address", "Phone Number"]
        field_type_dropdown = ttk.OptionMenu(zone_type_frame, field_type_var, field_types[0], *field_types, style='custom.TMenubutton')
        field_type_dropdown.pack(side="left", padx=5)
        canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()

        rect_id = self.canvas.create_rectangle(*coordinates, outline=color, width=2)
        zone = {
            'frame': frame,
            'entry': zone_entry,
            'field_type': field_type_var,
            'color': color,
            'rect': rect_id,
            'ocr_output': ocr_output_text,
            'original_coordinates': coordinates,
            'label': None,
            'selected': False,
        }


        self.zones_info.append(zone)
        zone['selected'] = False
        self.canvas.tag_bind(rect_id, "<Button-1>", lambda event, z=zone: self.on_zone_click(event, z))
        zone_entry.bind("<KeyRelease>", lambda event, z=zone: self.update_zone_label(z, event))
        for widget in [zone_entry, ocr_output_text, delete_btn, color_indicator, top_frame, field_type_dropdown, zone_type_label, zone_label, zone_name_frame, frame, zone_type_frame]:
            widget.bind("<MouseWheel>", self.scroll_zone_canvas)


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


    def select_zone(self, zone):
        for z in self.zones_info:
            z['selected'] = False
        zone['selected'] = True

    def delete_zone(self, frame):
        zone_index = None
        for i, zone in enumerate(self.zones_info):
            if zone['frame'] == frame:
                zone_index = i
                break
        if zone_index is not None:
            zone = self.zones_info.pop(zone_index)
            print(f"Deleting zone: {zone}") 
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
                ocr_output_text = self.perform_ocr_on_coordinates(scaled_coords)
                if save_crop_image:
                    cropped_image = self.crop_image(*coords)
                    cropped_image.save(os.path.join(cropped_images_dir, f"cropped_{image_count}.png"))
                image_count += 1
                zone['ocr_output'].delete(1.0, tk.END)
                zone['ocr_output'].insert(tk.END, ocr_output_text)
                print(f"{zone['entry'].get()}: {ocr_output_text}")


    def perform_ocr_on_coordinates(self, coordinates):
        x1, y1, x2, y2 = coordinates
        cropped_image = self.crop_image(x1, y1, x2, y2)
        cv_image = cv2.cvtColor(np.array(cropped_image), cv2.COLOR_RGB2BGR)
        ocr_result = self.ocr.ocr(cv_image)
        ocr_text = ' '.join([res[1][0] for sublist in ocr_result for res in sublist if res is not None])
        if ocr_result is None:
            ocr_text = ""

        return ocr_text
    
    def perform_ocr_on_zone(self, zone_info):
        print('zone info::', zone_info)
        if zone_info["rect"]:
            coords = self.canvas.coords(zone_info['rect'])
            scaled_coords = [c * self.canvas_scale for c in coords]
            ocr_output = self.perform_ocr_on_coordinates(scaled_coords)
            zone_info['ocr_output_text'] = ocr_output

        return zone_info
    
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
        super().__init__(parent, bg="#EEEEEE")
        self.wm_overrideredirect(True)
        self.zone_info = zone_info
        self.on_save = on_save
        self.on_delete = on_delete
        self.existing_zone_names = existing_zone_names
        self.init_ui()

    def init_ui(self):
        # ocr_text_label = tk.Label(self, text=self.zone_info['ocr_output_text'], bg="#EEEEEE")
        ocr_text_label = ctk.CTkLabel(self, text="This is a test.", fg_color="#EEEEEE")
        ocr_text_label.pack(padx=10, pady=10)

        self.label_var = tk.StringVar()
        label_dropdown = ttk.OptionMenu(self, self.label_var, "", *self.existing_zone_names)
        label_dropdown.pack(padx=5, pady=5)

        btn_frame = tk.Frame(self, bg="#EEEEEE")
        btn_frame.pack()

        delete_btn = ctk.CTkButton(btn_frame, text="Delete", command=self.delete_zone)
        delete_btn.bind("<Button-1>", self.delete_zone)
        delete_btn.pack(side=tk.LEFT, padx=10, pady=5)

        save_btn = ctk.CTkButton(btn_frame, text="Save", command=self.save_zone)
        save_btn.pack(side=tk.LEFT, padx=10, pady=5)

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

    def delete_zone(self, event=None):
        self.on_delete(self.zone_info)
        self.destroy()
        self.master.ignore_next_release = True



if __name__ == "__main__":
    app = ZonalOCRApplication()
    app.mainloop()