# OpenCarve
<div style="text-align: center;">
<img src="logo.png" alt="Overview Screen" width="200">
</div>

![Overview Screen](doc/OpenCarve.png)
OpenCarve is a tool for converting grayscale images (e.g. heightmaps) into G-code for 3D surface machining. The application offers an easy-to-use interface that lets you adjust parameters, generate optimized G-code, and visualize the resulting toolpath in 3D.

## Features

- **Image-to-G-Code Conversion:**  
  Converts grayscale images into precise G-code for CNC machining.
- **Parameter Configuration:**  
  Adjust settings such as pixel size, maximum depth, safe Z height, feed rates, spindle speed, step-down, and boundary margin.
- **3D Visualization:**  
  View the generated toolpath interactively in a 3D viewer.
- **G-Code Postprocessor:**  
  Optimizes the generated G-code by merging consecutive commands with identical parameters, reducing file size and improving execution.
- **Time Estimation:**  
  Provides an average processing time based on the generated G-code.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/OpenCarve.git

2. Install dependencies:
    ```bash
    pip install -r requirements.txt

(Make sure you have installed packages such as PyQt5, NumPy, Pillow, and PyOpenGL.)

## Usage
1. Run the application:
    ```bash
    python main.py

2. Load Image:

    Click the Load Image button to open a grayscale image.

3. Configure Parameters:

    Adjust parameters (pixel size, maximum depth, safe Z, feed rates, spindle speed, step-down, boundary margin) as needed.
4. Generate G-Code:

    Click Generate G-Code. The G-code is generated and displayed in a dedicated panel. You can then copy or save the G-code using the provided buttons.
5. Transfer G-Code:
    
    The generated G-code can be sent to your CNC machine.

Screenshots

### Overview Screen
![Overview Screen](doc/OpenCarve.png)

### 3D Visualization (Detail with Hidden Rapids)
![Overview Screen](doc/OpenCarve-3DVis-detail-hide-rapids.png)

### 3D Visualization (HSKL-Logo)
![Overview Screen](doc/OpenCarve-3DVis-hskl.png)

### Time Estimation Example

![Time Estimation](doc/OpenCarve-Time-Est.png)
### Example Heightmap
![Time Estimation](assets/topoheightmap.png)
## Technologies Used

+ Python: The main programming language.
+ PyQt5: For creating the graphical user interface.
+ OpenGL: For real-time 3D visualization of the toolpath.
+ NumPy & Pillow: For image processing and numerical computations.

## License

OpenCarve is licensed under the GNU GPLv2. See LICENSE for details.
Contributing

Contributions are welcome! Please fork the repository and submit your pull requests.