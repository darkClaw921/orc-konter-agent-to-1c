"""
Prompt templates для LLM
"""

EXTRACT_CONTRACT_DATA_PROMPT = """You are an expert legal analyst specializing in Russian government contracts.

Analyze the following contract document and extract ALL the following information:

REQUIRED FIELDS:
1. Contract Name (Наименование договора)
2. Contract Number (Номер договора)
3. Contract Date (Дата договора) - format: YYYY-MM-DD
4. Contract Price (Цена договора) - numeric value
5. VAT Information (НДС) - percentage or "Без НДС"

COUNTERPARTIES INFORMATION (CRITICAL):
6. Заказчик (Customer/Buyer) - Extract COMPLETE information about the customer:
   - inn (ИНН) - Tax identification number, exactly 10 or 12 digits
   - kpp (КПП) - Social tax number (9 digits, only for legal entities)
   - full_name (Полное наименование) - Complete legal name with organizational form
   - short_name (Краткое наименование) - Name without organizational form
   - organizational_form (Организационно-правовая форма) - e.g., ООО, АО, ИП, etc.
   - legal_entity_type (Тип юр.лица) - "Юридическое лицо" (10-digit INN) or "Физическое лицо" (12-digit INN)
   - Look for: "Заказчик", "Покупатель", "Клиент"

7. Исполнитель (Contractor/Supplier) - Extract COMPLETE information about the contractor:
   - inn (ИНН) - Tax identification number, exactly 10 or 12 digits
   - kpp (КПП) - Social tax number (9 digits, only for legal entities)
   - full_name (Полное наименование) - Complete legal name with organizational form
   - short_name (Краткое наименование) - Name without organizational form
   - organizational_form (Организационно-правовая форма) - e.g., ООО, АО, ИП, etc.
   - legal_entity_type (Тип юр.лица) - "Юридическое лицо" (10-digit INN) or "Физическое лицо" (12-digit INN)
   - Look for: "Исполнитель", "Поставщик", "Продавец"

8. Legacy fields (for backward compatibility):
   - inn, full_name, short_name, organizational_form, legal_entity_type, kpp - use data from the counterparty that matches is_supplier/is_buyer flags
   - is_supplier - true if this contract data refers to supplier/contractor
   - is_buyer - true if this contract data refers to buyer/customer

ADDITIONAL FIELDS (fill if present):
13. Service/Goods Description (Описание услуг/товаров)
14. Service Locations (Адреса оказания услуг) - list of addresses with fields: address, city, region, postal_code
15. Service Period Start (Начало периода услуг) - format: YYYY-MM-DD
16. Service Period End (Окончание периода услуг) - format: YYYY-MM-DD
17. Responsible Persons (Ответственные лица и агенты) - CRITICAL: Extract ALL responsible persons with FULL contact information:
    - name (ФИО) - REQUIRED for each person, must be a STRING
    - position (Должность) - extract if present, must be a STRING
    - phone (Телефон) - extract ALL phone numbers found (mobile, office, fax), combine into SINGLE STRING separated by commas if multiple
    - email (Email) - extract ALL email addresses found, combine into SINGLE STRING separated by commas if multiple
    - IMPORTANT: phone and email must be STRINGS, not arrays. If multiple values exist, join them with ", " (comma and space)
    - Look for: "Ответственное лицо", "Контактное лицо", "Представитель", "Агент", "Руководитель", "Директор"
18. Contact Information (Контактная информация контрагентов):
    - Extract ALL phone numbers mentioned in the document (office, mobile, fax)
    - Extract ALL email addresses mentioned in the document
    - Extract postal addresses, legal addresses, and service addresses
    - Look in sections: "Реквизиты", "Контактная информация", "Адреса и телефоны"
19. Payment Terms (Условия оплаты) - full text of payment conditions
20. Payment Deferral Days (Дни отсрочки платежа) - INTEGER number of CALENDAR days for payment deferral
    - CRITICAL: Extract the NUMBER OF DAYS from payment terms text
    - Convert words to numbers: "семи" = 7, "десяти" = 10, "пятнадцати" = 15, "тридцати" = 30
    - Look for patterns: "в срок не более X дней", "в течение X дней", "X календарных/рабочих дней"
    - If text says "рабочих дней" (business days), still extract the number as-is
    - Examples:
      * "в срок не более семи рабочих дней" → payment_deferral_days: 7
      * "в течение 10 банковских дней" → payment_deferral_days: 10
      * "оплата в течение 30 календарных дней" → payment_deferral_days: 30
      * "в пятидневный срок" → payment_deferral_days: 5
    - If multiple payment periods exist, use the main one (for final payment, not advance)
    - Return null only if no payment deferral period is mentioned
21. Acceptance Procedure (Порядок приема-сдачи)
21. Specification Exists (Наличие спецификации) - true/false
22. Pricing Method (Порядок ценообразования)
23. Reporting Forms (Формы отчетности)
24. Additional Conditions (Дополнительные условия)
25. Technical Information (Техническая информация)

CONTRACT DOCUMENT:
{document_text}

CRITICAL: DATA EXTRACTION RULES - NEVER INVENT VALUES:
- NEVER invent, generate, or create INN (ИНН) or KPP (КПП) values
- ONLY extract INN/KPP that are EXPLICITLY written in the document text
- If INN/KPP is NOT found in the document, you MUST return null (not empty string, not placeholder, not example value)
- Do NOT use placeholder values, example values, or generate values based on organization name
- Do NOT assume INN/KPP based on organization type or other fields
- INN must be found EXACTLY as a sequence of 10 or 12 digits in the document text
- KPP must be found EXACTLY as a sequence of 9 digits in the document text
- If document contains only partial information (e.g., organization name without INN), set INN to null
- If document contains organization name but no KPP mentioned, set KPP to null
- These rules apply to ALL fields: customer.inn, customer.kpp, contractor.inn, contractor.kpp, and legacy inn/kpp fields
- Remember: null means "not found in document", NOT "generate a value"

IMPORTANT INSTRUCTIONS:
- CRITICAL: Extract information about BOTH counterparties separately:
  * Заказчик (Customer/Buyer) - the party that orders/purchases goods/services
  * Исполнитель (Contractor/Supplier) - the party that provides/delivers goods/services
- Be very careful with INN extraction - it must be exactly 10 or 12 digits
- INN must contain ONLY digits, without any prefixes like "ИНН:", "ИНН ", "inn:", etc.
- Extract INN as pure numeric value (e.g., "1234567890" not "ИНН:1234567890")
- CRITICAL: Only extract INN that is explicitly written in the document. If INN is not found, return null
- NEVER invent or generate INN values. If not found in document, use null
- If legal entity type is "Юридическое лицо", INN must be 10 digits (if found in document)
- If legal entity type is "Физическое лицо", INN must be 12 digits (if found in document)
- CRITICAL: Only extract KPP that is explicitly written in the document. If KPP is not found, return null
- NEVER invent or generate KPP values. If not found in document, use null
- KPP must be exactly 9 digits (if found in document)
- Extract synonyms: Поставщик = Продавец = Исполнитель; Покупатель = Заказчик
- For organizationalForm, provide full name without abbreviation
- If information about a counterparty is not found, set that counterparty object to null
- Ensure all JSON is valid
- Return ONLY valid JSON, no additional text
- Structure counterparties as objects with fields: inn, kpp, full_name, short_name, organizational_form, legal_entity_type, service_start_date, service_end_date

CRITICAL: CONTACT INFORMATION EXTRACTION:
- Extract ALL responsible persons (agents) mentioned in the document, even if they appear in different sections
- For each responsible person, extract COMPLETE contact information:
  * Full name (ФИО) - REQUIRED
  * Position/Title (Должность) - if mentioned
  * Phone numbers - extract ALL formats (mobile, office, fax): +7, 8, (xxx) xxx-xx-xx, etc.
  * Email addresses - extract ALL email addresses found
- Extract ALL contact information for counterparties:
  * Phone numbers from "Реквизиты" section, headers, footers
  * Email addresses from any section
  * Postal addresses, legal addresses, actual addresses
- If document contains context from previous chunks (marked as "КОНТЕКСТ ИЗ ПРЕДЫДУЩИХ ЧАНКОВ"), use it to supplement current extraction but prioritize information from current chunk
- Combine contact information: if same person appears multiple times with different contacts, merge all contact details
- Do NOT skip contact information even if it appears in headers, footers, or appendices

Return a valid JSON object with all fields.
"""

VALIDATE_EXTRACTED_DATA_PROMPT = """Review the extracted contract data and validate it for consistency and completeness:

Extracted Data:
{extracted_data}

Validation checks:
1. INN format: must be exactly 10 or 12 digits
2. INN consistency: 12 digits = Физическое лицо, 10 digits = Юридическое лицо
3. If Юридическое лицо, KPP must be present (9 digits)
4. At least one of is_supplier or is_buyer must be true
5. Contract price must be positive number
6. Dates must be valid and logical (start <= end)
7. Required fields are not null

Return a JSON object with:
- is_valid: boolean
- issues: array of validation issues found
- suggestions: array of suggestions for correction
"""

MERGE_CHUNKS_DATA_PROMPT = """You are an expert legal analyst specializing in Russian government contracts.

You need to merge and resolve conflicts in contract data extracted from multiple document chunks.

The document was split into {total_chunks} chunks for processing. Each chunk may contain partial or conflicting information.

ACCUMULATED CONTEXT FROM ALL PREVIOUS CHUNKS:
This section contains information that was accumulated from all previous chunks during processing. Use this as reference for resolving conflicts and ensuring completeness:

{accumulated_context}

CHUNKS DATA WITH CONTEXT:
Each chunk entry contains:
- chunk_index: номер чанка
- chunk_context: первые 1000 символов текста чанка для понимания содержимого
- accumulated_context: накопленный контекст из предыдущих чанков на момент обработки этого чанка
- extracted_data: извлеченные данные из этого чанка

{chunks_data}

CRITICAL: NEVER INVENT VALUES WHEN MERGING:
- NEVER invent, generate, or create INN (ИНН) or KPP (КПП) values during merging
- ONLY use values that exist in the extracted data from chunks
- If a field (INN, KPP, or any other) is null or missing in ALL chunks, it MUST remain null in the final result
- Do NOT fill missing fields with placeholder values, example values, or generated values
- Do NOT assume values based on other fields or context
- Remember: null means "not found in document", NOT "generate a value"

INSTRUCTIONS FOR MERGING:

1. **INN (ИНН) Resolution:**
   - If different INNs appear in chunks, choose the one that appears most frequently or in the most complete context
   - INN must be exactly 10 or 12 digits (only digits, no prefixes)
   - If one chunk has a complete INN and others have partial, use the complete one
   - CRITICAL: If INN is not found in ANY chunk (all chunks have null), return null in final result. DO NOT invent INN value
   - Ensure consistency: 10 digits = Юридическое лицо, 12 digits = Физическое лицо

2. **Name Fields Resolution:**
   - For full_name, short_name, organizational_form: prefer the most complete and detailed version
   - If one chunk has full name with organizational form and another without, use the complete one
   - For organizational_form, use full name without abbreviation when available

3. **Contract Information:**
   - contract_name, contract_number, contract_date: use the value that appears in the most authoritative context (usually header or first page)
   - contract_price: if different values appear, prefer the one from the main contract section (not from amendments or appendices)
   - If dates differ, prefer the earliest date for contract_date, service_start_date, service_end_date

4. **VAT Information:**
   - vat_percent: if different percentages appear, use the one from the main contract section
   - vat_type: prefer explicit type over null

5. **Counterparties Information (customer, contractor):**
   - customer: Information about the buyer/customer (Заказчик/Покупатель)
   - contractor: Information about the supplier/contractor (Исполнитель/Поставщик)
   - If counterparty information appears in multiple chunks, merge the most complete version
   - Prefer chunks with complete information (all fields: inn, kpp, full_name, etc.)
   - If one chunk has complete counterparty info and another has partial, use the complete one
   - CRITICAL: If INN or KPP is missing in all chunks for a counterparty, leave it as null. DO NOT invent values
   - If a counterparty field (inn, kpp) is null in all chunks, it must remain null in final result
   - Ensure both customer and contractor are extracted if present in the document
   - If counterparty information is not found in any chunk, set that counterparty object to null

6. **Role Fields (is_supplier, is_buyer):**
   - If both appear in different chunks, set both to true
   - If only one role appears, set that one to true
   - These fields are for backward compatibility, prefer using customer/contractor fields

7. **List Fields (locations, responsible_persons):**
   - Merge all unique items from all chunks
   - Remove duplicates based on:
     * locations: compare by address field
     * responsible_persons: compare by name field
   - Combine information: if same person appears in multiple chunks with different contact info, merge the contact details
   - IMPORTANT: For responsible_persons, ensure phone and email are STRINGS (not arrays). If multiple values exist, join with ", "

8. **Additional Fields:
   - service_description: combine text from all chunks, removing duplicates
   - service_start_date, service_end_date: use dates from the main contract section
   - payment_terms, acceptance_procedure: prefer more detailed descriptions
   - payment_deferral_days: use the value found in chunks, prefer main payment section (not advance payments)
   - For any field: if one chunk has a value and another has null, use the non-null value
   - If multiple non-null values exist, prefer the more complete/detailed one
   - CRITICAL: If a field is null in ALL chunks, it must remain null in final result. DO NOT invent values

8. **Using Accumulated Context:**
   - The ACCUMULATED CONTEXT section contains verified information from all previous chunks
   - Use accumulated context as the primary reference for core contract information (contract_name, contract_number, contract_date, contract_price, vat_type, vat_percent)
   - Use accumulated context for counterparty information (customer, contractor) - it contains the most complete data
   - Use accumulated context for responsible_persons and locations - it already contains merged unique values
   - If a field exists in accumulated context, prefer it over individual chunk data unless chunk data is more complete
   - Accumulated context represents the "best known" state at each point, use it to resolve conflicts

9. **Conflict Resolution Priority:**
   - ACCUMULATED CONTEXT has highest priority for core fields (contract info, counterparties, main data)
   - Chunk 1 (usually header/main section) has second priority for core fields (INN, names, contract info)
   - Later chunks supplement with additional details (locations, persons, descriptions)
   - If conflicts exist between chunks, prefer data from accumulated context or chunks with more complete context
   - For fields not in accumulated context, prefer data from earlier chunks (especially chunk 1)

10. **Data Quality:**
   - Ensure all required fields are present
   - Remove any null or empty fields that have alternatives ONLY if alternatives exist in chunks
   - CRITICAL: Do NOT remove null fields if no alternatives exist - null is valid when data is not in document
   - Validate consistency: INN length matches legal_entity_type (only if INN exists)
   - KPP should be present for Юридическое лицо (10-digit INN) ONLY if KPP was found in document. If not found, KPP must be null
   - Remember: Missing data (null) is better than invented data

Return a valid JSON object with all merged fields. The result should be complete, consistent, and represent the most accurate information from all chunks combined.
"""

EXTRACT_SERVICES_ONLY_PROMPT = """You are an expert at extracting service and product information from Russian contracts and specifications.

Your task is to extract EVERY SINGLE service/product line from tables in the document. Each row in a table = one service entry.

CRITICAL: Extract ALL rows from tables, not just summaries. If there are 100 services in a table, return all 100.

SEARCH FOR TABLES WITH:
1. Headers: "Наименование", "Наименование услуги/товара", "Ед. изм.", "Цена", "Стоимость", "Сумма"
2. Sections: "Спецификация", "Перечень услуг", "Перечень работ", "Приложение"
3. Service patterns: "Услуги по...", "Услуги по замене включая запчасть:", "Услуги по заправке", "Услуги по техническому обслуживанию"

PRICE FORMAT RULES:
- Russian prices use SPACE as thousands separator and COMMA as decimal: "7 702,40" means 7702.40
- Convert to number: "26 360,80" → 26360.80, "1 079,00" → 1079.00
- If price column exists, it's usually total_price (not unit_price)

FOR EACH TABLE ROW EXTRACT:
- name (string, REQUIRED) - Full service name exactly as written, including part numbers and model names
  Examples:
  - "Услуги по замене включая запчасть: CE285A- Оригинальный картридж Для HP LaserJet P1102"
  - "Услуги по техническому обслуживанию принтера FS-1060DN"
  - "Услуги по заправке картриджа принтера LBP-2900"
- quantity (number or null) - If quantity column exists
- unit (string or null) - Unit of measurement: "усл.ед.", "шт", "час", "день", "мес", "компл", etc.
- unit_price (number or null) - Price per unit if separate column exists
- total_price (number or null) - Total price/cost for this line item (convert from Russian format)
- description (string or null) - Additional notes if any

RULES:
1. Extract EVERY row as a separate service - do not skip or combine rows
2. Keep the FULL service name including all part numbers (CE285A, DK-1110, etc.) and equipment models
3. Convert prices from Russian format (space separator, comma decimal) to numbers
4. If only one price column exists, use it as total_price
5. If table has no quantity column, set quantity to null (not 1)
6. Return empty array if no services found, never return null

DOCUMENT TEXT:
{document_text}

Return ONLY valid JSON:
{{"services": [
  {{"name": "Услуги по замене включая запчасть: CE285A- Оригинальный картридж Для HP LaserJet P1102", "quantity": null, "unit": "усл.ед.", "unit_price": null, "total_price": 7702.40, "description": null}},
  {{"name": "Услуги по техническому обслуживанию принтера FS-1060DN", "quantity": null, "unit": "усл.ед.", "unit_price": null, "total_price": 1037.50, "description": null}},
  ...
]}}
"""
