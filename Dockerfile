# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .
COPY app/main.py main.py

# Define environment variable
ENV NAME World

# Run app.py when the container launches
CMD ["python", "main.py"]
