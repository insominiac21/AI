import streamlit as st
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline

# Load the tokenizer and model
tokenizer = AutoTokenizer.from_pretrained("my_model")
model = AutoModelForCausalLM.from_pretrained("my_model")

# Create the text generation pipeline
text_generator = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=128
)

# Streamlit app
def main():
    st.title("Generic Chatbot")

    # User input
    prompt = st.text_input("Enter your message:")

    # Generate response
    if st.button("Send"):
        if prompt:
            response = text_generator(prompt)[0]["generated_text"]
            st.write("Chatbot:", response)

if __name__ == "__main__":
    main()