from transformers import pipeline, AutoModelForSequenceClassification, AutoTokenizer
import torch
import torch.nn.functional as F
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
import re
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FinancialNLU:
    def __init__(self):
        # Initialize the financial intent classifier with CPU optimization
        self.intent_model_name = "facebook/bart-large-mnli"
        
        # Check for CUDA and set device
        self.device = 0 if torch.cuda.is_available() else -1
        
        # Load model with optimizations
        torch.set_num_threads(1)  # Limit CPU threads to prevent overloading
        
        logger.info(f"Loading NLP model on {'GPU' if self.device == 0 else 'CPU'}")
        start_time = time.time()
        
        # Use a smaller model for faster inference
        self.intent_classifier = pipeline(
            "zero-shot-classification",
            model=self.intent_model_name,
            device=self.device,
            torch_dtype=torch.float16 if self.device == 0 else torch.float32
        )
        
        # Warm up the model
        if self.device == 0:  # Only warm up on GPU
            self.intent_classifier("warm up", ["greeting", "goodbye"], multi_label=False)
            
        logger.info(f"NLP model loaded in {time.time() - start_time:.2f} seconds")
        
        # Define financial intents and their patterns
        self.intents = {
            "affirmative": [
                "yes", "y", "ya", "yeah", "yep", "sure", "ok", "okay", "alright", "definitely",
                "absolutely", "certainly", "of course", "why not", "i do", "i would", "i want to",
                "sounds good", "sure thing", "yes please", "yes i do", "yes i would", "yes i want to"
            ],
            "negative": [
                "no", "n", "nope", "nah", "not really", "i don't think so", "i don't want to",
                "maybe later", "not now", "i'll pass", "no thanks", "not interested"
            ],
            "greeting": ["hello", "hi", "hey", "greetings"],
            "goodbye": ["bye", "goodbye", "see you", "farewell"],
            "ask_about_plans": [
                "what plans do you have", "recommend a plan", "what's available",
                "insurance options", "what can you offer"
            ],
            "ask_about_premiums": [
                "how much does it cost", "premium rates", "what's the price",
                "monthly payment", "how much to pay"
            ],
            "ask_about_coverage": [
                "what's covered", "what does it include", "coverage details",
                "what are the benefits", "what protection do I get"
            ],
            "ask_about_claims": [
                "how to claim", "claims process", "file a claim",
                "claim procedure", "how to get reimbursement"
            ],
            "express_concern": [
                "I'm worried about", "concerned about", "not sure if",
                "afraid that", "worried that"
            ],
            "provide_personal_info": [
                "my name is", "I am", "I'm from", "my email is",
                "contact me at", "call me"
            ]
        }
        
        # Financial entities to extract
        self.financial_entities = {
            "amount": r"(RM|\$)?\s*\d+(?:[.,]\d{2})?\b",
            "time_period": r"(monthly|yearly|annually|per month|per year|each month|each year)",
            "coverage_type": r"(life insurance|medical|critical illness|accident|savings|investment|retirement)",
            "family_member": r"(my (?:son|daughter|children|child|wife|husband|spouse|partner|parents))"
        }
        
        # Response templates
        self.response_templates = {
            "greeting": [
                "Hello! I'm your financial assistant. How can I help you today?",
                "Hi there! I'm here to help with your financial planning needs.",
                "Welcome! How can I assist you with your financial goals today?"
            ],
            "goodbye": [
                "Thank you for chatting! Feel free to come back if you have more questions.",
                "Goodbye! Wishing you financial success!",
                "Take care! Remember to review your financial plan regularly."
            ],
            "fallback": [
                "I'm not sure I understand. Could you rephrase that?",
                "I want to make sure I help you correctly. Could you provide more details?",
                "I'm still learning about financial planning. Could you ask in a different way?"
            ]
        }
    
    def is_affirmative(self, text: str, threshold: float = 0.7) -> bool:
        """Check if the user's response is affirmative.
        
        Args:
            text: User's input text
            threshold: Confidence threshold (0-1) for considering a match
            
        Returns:
            bool: True if the response is affirmative, False otherwise
        """
        if not text.strip():
            return False
            
        # Simple keyword matching first (faster)
        text_lower = text.lower()
        for phrase in self.intents["affirmative"]:
            if phrase in text_lower:
                return True
                
        # If no direct match, use the classifier
        try:
            result = self.intent_classifier(
                text,
                candidate_labels=["affirmative", "negative"],
                multi_label=False
            )
            
            return (result["labels"][0] == "affirmative" and 
                   result["scores"][0] >= threshold)
            
        except Exception as e:
            logger.error(f"Error in is_affirmative: {e}")
            return False
            
    def is_negative(self, text: str, threshold: float = 0.7) -> bool:
        """Check if the user's response is negative.
        
        Args:
            text: User's input text
            threshold: Confidence threshold (0-1) for considering a match
            
        Returns:
            bool: True if the response is negative, False otherwise
        """
        if not text.strip():
            return False
            
        # Simple keyword matching first (faster)
        text_lower = text.lower()
        for phrase in self.intents["negative"]:
            if phrase in text_lower:
                return True
                
        # If no direct match, use the classifier
        try:
            result = self.intent_classifier(
                text,
                candidate_labels=["affirmative", "negative"],
                multi_label=False
            )
            
            return (result["labels"][0] == "negative" and 
                   result["scores"][0] >= threshold)
            
        except Exception as e:
            logger.error(f"Error in is_negative: {e}")
            return False
    
    def detect_intent(self, text: str) -> Tuple[str, float]:
        """Detect the intent of the user's message with optimizations."""
        if not text.strip():
            return "unknown", 0.0
            
        # First check for yes/no responses
        if self.is_affirmative(text):
            return "affirmative", 0.9
        elif self.is_negative(text):
            return "negative", 0.9
            
        # Convert intents to list of candidate labels
        candidate_labels = [k for k in self.intents.keys() 
                          if k not in ["affirmative", "negative"]]
        
        try:
            # Get prediction
            result = self.intent_classifier(
                text,
                candidate_labels=candidate_labels,
                multi_label=False
            )
            
            # Return the top intent with confidence
            return result["labels"][0], float(result["scores"][0])
            
        except Exception as e:
            logger.error(f"Error in detect_intent: {e}")
            return "error", 0.0
    
    def extract_entities(self, text: str) -> Dict[str, List[str]]:
        """Extract financial entities from the user's message."""
        entities = {}
        
        for entity_type, pattern in self.financial_entities.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                entities[entity_type] = list(set(matches))  # Remove duplicates
        
        return entities
    
    def generate_response(self, intent: str, entities: Dict[str, List[str]] = None) -> str:
        """Generate a natural response based on intent and entities."""
        if intent in self.response_templates:
            responses = self.response_templates[intent]
            return np.random.choice(responses)
        
        # Default response if intent not found
        return self.response_templates["fallback"][0]
    
    async def process(self, message: str) -> Dict[str, any]:
        """Process a message and return the intent, entities, and response."""
        # Clean the message
        message = message.lower().strip()
        
        # Detect intent
        intent, confidence = self.detect_intent(message)
        
        # Extract entities
        entities = self.extract_entities(message)
        
        # Generate response
        response = self.generate_response(intent, entities)
        
        return {
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
            "response": response
        }

# Singleton instance
nlp_processor = FinancialNLU()
