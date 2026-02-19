import pandas as pd
import tensorflow as tf
import numpy as np

def train_model():
    print("Loading Data...")

    # LOAD DATA
    try:
        # engine='python' and on_bad_lines='skip' help avoid basic parsing errors
        df = pd.read_csv("training_data.csv", on_bad_lines='skip', engine='python')
    except FileNotFoundError:
        print("Training data file 'training_data.csv' not found. Please run the scraper first.")
        return

    # --- DEBUGGING BLOCK ---
    print("\n" + "="*50)
    print("DATA INSPECTION (First 3 rows):")
    print(df.head(3)) 
    print("="*50 + "\n")
    # -----------------------

    # --- ROBUST DATA CLEANING ---
    print(f"Original row count: {len(df)}")
    
    # Force 'Rating' to be numeric. Any text (like "This is a...") becomes NaN
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce')
    
    # Drop rows where Rating is NaN or Text is missing
    df = df.dropna(subset=['Rating', 'Text'])
    
    # Ensure all text is treated as strings
    df['Text'] = df['Text'].astype(str)
    
    print(f"Cleaned row count: {len(df)}")
    
    if len(df) == 0:
        print("   CRITICAL ERROR: All rows were deleted during cleaning.")
        print("   Likely Cause: Your 'Rating' column contains Text, or the CSV is empty.")
        return

    # 2. LABEL DATA
    # Logic: > 3.0 stars is Positive (1), <= 3.0 is Negative (0)
    df['Label'] = df['Rating'].apply(lambda x: 1 if x > 3.0 else 0)
    
    # Shuffle the data
    df = df.sample(frac=1).reset_index(drop=True)

    # Prepare Inputs (X) and Targets (y)
    texts = tf.constant(df['Text'].tolist())
    labels = tf.constant(df['Label'].tolist())

    print("Tokenizing Text...")
    print(f"Total samples: {len(texts)}")

    # VECTORIZATION
    max_tokens = 10000
    vectorize_layer = tf.keras.layers.TextVectorization(max_tokens=max_tokens, output_mode='int')
    vectorize_layer.adapt(texts)

    # BUILD MODEL
    model = tf.keras.Sequential([
        tf.keras.Input(shape=(1,), dtype=tf.string),
        vectorize_layer,
        tf.keras.layers.Embedding(input_dim=max_tokens, output_dim=128),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(64, activation='relu'),
        tf.keras.layers.Dense(1, activation='sigmoid')
    ])

    # COMPILE MODEL
    model.compile(loss='binary_crossentropy', optimizer='adam', metrics=['accuracy'])

    # TRAIN MODEL
    history = model.fit(texts, labels, epochs=25, batch_size=32, validation_split=0.2)

    # TEST MODEL
    print("\nTraining Complete. Testing Model...")
    test_reviews = [
        "I absolutely loved this product! It exceeded my expectations.",
        "This is the worst purchase I've ever made. Completely disappointed.",
        "It was okay, not great but not terrible either."
    ]
    
    # Convert test reviews to Tensor as well for consistency
    test_tensor = tf.constant(test_reviews)
    predictions = model.predict(test_tensor)
    
    print("\n" + "="*50)
    for review, prediction in zip(test_reviews, predictions):
        score = prediction[0]
        sentiment = "Positive" if score >= 0.5 else "Negative"
        print(f"Review: {review[:60]}...")
        print(f"Predicted Sentiment: {sentiment} (Confidence: {score:.2f})")
        print("-" * 30)

if __name__ == "__main__":
    train_model()