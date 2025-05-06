# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app
# Ensure the main.py file is copied correctly
COPY app/main.py main.py

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt


# Define environment variable
ENV NAME World

# Run app.py when the container launches
CMD ["python", "main.py"]
