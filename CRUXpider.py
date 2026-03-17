import os
import pandas as pd
import argparse
import arxiv
import csv
import datetime
from pyalex import Works
import pyalex
from collections import deque

try:
    from paperswithcode import PapersWithCodeClient
except ImportError:
    PapersWithCodeClient = None

def parse_file(file):
        #use pandas to parse the input file 
    # df = pd.read_csv(file, header = None, names = ['Published_Journal','PaperTitle'])
    df = pd.read_csv(file, header = None, names = ['PaperTitle'])
    df = df.dropna()
    return df

class CRUXiperRW:
    # apikey = "ab939f5097d218f54bc4c6a85fb894f54b3f555d"
    # client = PapersWithCodeClient(token = apikey)

    def __init__(self, client, df):
        self.client = client
        self.df = df
    
    def get_journal(self):
        print("Querying Publication Information from Arxiv...")
        result_series = pd.Series(dtype = object)
        for index,row in self.df.iterrows():
            self.title = row['PaperTitle']
            search = arxiv.Search(
                query = 'ti:{}'.format(self.title),
                max_results=1
                )
            result = None # default
            for results in search.results():
                result = results.journal_ref
            if result:
                result_series.at[index] = result
                self.df = self.df.assign(Published_Journal = result_series)
    
    def get_PaperURL(self):
        print("Querying Paper URLs from Arxiv...")
        result_series = pd.Series(dtype = object)
        for index,row in self.df.iterrows():
            self.title = row['PaperTitle']
            search = arxiv.Search(
                query = 'ti:{}'.format(self.title),
                max_results=1
                )
            result = None # default
            for results in search.results():
                result = results.pdf_url
            if result:
                result_series.at[index] = result
                self.df = self.df.assign(pdfURL = result_series)
        
    def get_Categories(self):
        print("Querying Categories Information from Arxiv...")
        result_series = pd.Series(dtype = object)
        result_seriesx = pd.Series(dtype = object)
        for index,row in self.df.iterrows():
            self.title = row['PaperTitle']
            search = arxiv.Search(
                query = 'ti:{}'.format(self.title),
                max_results=1
                )
            result = None # default
            for results in search.results():
                result = results.categories
            if result:
                result_series.at[index] = result
                if ('stat.ML' in result_series.at[index] or
                    'cs.AI' in result_series.at[index] or
                    'cs.CV' in result_series.at[index] or
                    'cs.LG' in result_series.at[index]):
                    result_seriesx.at[index] = 'YES'

                else:
                    result_seriesx.at[index] = 'NO'

                self.df = self.df.assign(Categories = result_series)
                self.df = self.df.assign(IfAIRelated = result_seriesx)

    def get_PaperID(self):
        #suppose the inputs are actual title
        #find the match, if matches, add a new column, otherwise, pass
        result_series = pd.Series(dtype = object)
        if self.client is None:
            self.df = self.df.assign(PaperID=result_series)
            return
        for index,row in self.df.iterrows():
            self.title = row['PaperTitle']
            if self.title is not None:
                paperID = self.client.paper_list(self.title)
                if paperID.count == 1:
                    result = paperID.results[0].id
                    result_series.at[index] = result
                    self.df = self.df.assign(PaperID = result_series)
                elif paperID.count == 0:
                    #error handling is taken care of
                    print("Paper < ",self.title," > is not found")
                    result = None
                    result_series.at[index] = result
                    self.df = self.df.assign(PaperID = result_series)
                    continue
                elif paperID.count > 1:
                    print("Title",self.title,"is too Vague.",
                        "Possibly inaccurate match is provided & Please inspect")
                    result = paperID.results[0].id
                    result_series.at[index] = result
                    self.df = self.df.assign(PaperID = result_series)




    def get_Dataset(self):
        #error handling, we don't know if the paper'ID is a valid Paper-With-Code ID
        result_series = pd.Series(dtype = object)
        if self.client is None:
            self.df = self.df.assign(Datasets=result_series)
            return
        for index,row in self.df.iterrows():
            paperID = row['PaperID']
            if paperID:
                try:
                    paperdataset = self.client.paper_dataset_list(paperID)
                    result = paperdataset.results
                    
                    result_series.at[index] = result
                    # print(result)
                    
                    self.df = self.df.assign(Datasets = result_series)

                except Exception as e:
                    print("Dataset of < ",self.title," > is not found", str(e))
                    pass

        #paperdataset = self.client.paper_dataset_list(paperID)

    def get_Methods(self):
        result_series = pd.Series(dtype = object)
        if self.client is None:
            self.df = self.df.assign(Methods=result_series)
            return
        for index,row in self.df.iterrows():
            paperID = row['PaperID']
            if paperID:
                try:
                    methodmentioned = self.client.paper_method_list(paperID)
                    methodresults = methodmentioned.results
                    methodlist = []
                    for i in range(len(methodresults)):
                        methodname = methodresults[i].name
                        methodlist.append(methodname)
                    result_series.at[index] = methodlist
                    self.df = self.df.assign(Methods = result_series)

                except Exception as e:
                    print("Methods of",self.title,"is not found", str(e))
                    pass

    def get_repository(self):
        result_series = pd.Series(dtype = object)
        if self.client is None:
            self.df = self.df.assign(RepositoryURL=result_series)
            return
        for index,row in self.df.iterrows():
            paperID = row['PaperID']
            if paperID:
                try:
                    Repo = self.client.paper_repository_list(paperID)
                    if Repo.results:
                        repo = Repo.results[0].url
                        result_series.at[index] = repo
                        self.df = self.df.assign(RepositoryURL = result_series)

                except Exception as e:
                    print("Repository of",self.title,"is not found", str(e))
                    pass
    def write_to_output(self, out_path):
        self.df.to_csv(out_path, index = False)

    def get_repo_topics(self):
        print("GitHub topic enrichment is disabled in the open-source version.")

    
                




class CRUXpidergetPaper:

    def __init__(self, Venue, num, targetTime, targetPath):
        self.Venue = Venue
        self.num = num
        self.targetTime = targetTime
        self.targetPath = targetPath 
        #targetTime format: 2023,1,1: 2023 January 1st

    def fromVenueGet(self):
        year, month, date = map(int, self.targetTime.split(','))
        start_date = datetime.date(year, month, date)
        end_date = datetime.date.today()


        with open(self.targetPath, 'w', newline='') as csv_file:
            writer = csv.writer(csv_file)
            search = arxiv.Search(
                query = 'jr:{} AND submittedDate:[{} TO {}]'.format(self.Venue,start_date.strftime('%Y%m%d'), end_date.strftime('%Y%m%d')),
                sort_by = arxiv.SortCriterion.SubmittedDate,
                max_results = int(self.num)
            )
            for result in search.results():
                writer.writerow([result.title])
                # print(result.title)

class CRUXpideraddPaper:
    def __init__(self, targetPath, paperList):
        self.targetPath = targetPath
        self.paperList = paperList

    def AddtoFile(self):
        with open(self.targetPath, mode = 'a', newline='') as csv_file:
            writer = csv.writer(csv_file)
            for title in self.paperList:
                writer.writerow([title])

class CRUXpiderRelevantPaper:
    pyalex.config.email = os.getenv("PYALEX_EMAIL", pyalex.config.email)
    def __init__(self, inputFile, maxNum, outputFile):
        self.inputFile = inputFile
        self.maxNum = int(maxNum)
        self.outputFile = outputFile

    def get_Relevant_Paper(self):
        self.inputDF = pd.read_csv(self.inputFile, header = None)
        #search for each title's openalex id
        #add Dataframe elements to a queue
        queue = deque()
        for row in self.inputDF.values:
            queue.append(row)
        while queue:
            current = queue.popleft()
            try:
                SearchforID = Works().search_filter(title=current).get()
                ID = 'W' + SearchforID[0]['ids']['mag']
                relevantIDURLlist = Works()[ID]["related_works"]
                parsed_IDlist = [url.replace('https://openalex.org/', '') for url in relevantIDURLlist]
                for id in parsed_IDlist:
                    w = Works()[id]
                    title = w["title"]
                    print(title)
                    queue.append(title)
            except:
                pass
            if len(queue) >= self.maxNum:
                break

        for title in queue:
            self.inputDF.loc[len(self.inputDF)] = [title]
            self.inputDF = self.inputDF.drop_duplicates()
        #just to demonstrate
        print(self.inputDF)

        self.inputDF.to_csv(self.outputFile, index = False, header = False)



        # for index, row in self.inputDF.iterrows():
        #     row_str = f'{row.iloc[0]}'
        #     SearchforID = Works().search_filter(title=row_str).get()
        #     ID = 'W' + SearchforID[0]['ids']['mag']
        #     #get relevant paper
        #     relevantIDURLlist = Works()[ID]["related_works"]
        #     parsed_IDlist = [url.replace('https://openalex.org/', '') for url in relevantIDURLlist]
        #     for id in parsed_IDlist:
        #         w = Works()[id]
        #         title = w["title"]
        #         print(title)
        #         self.inputDF.loc[len(self.inputDF)] = [title]
        #     # print(len(self.inputDF))
                    
   



def main():
    apikey = os.getenv("PAPERSWITHCODE_API_KEY", "")
    client = PapersWithCodeClient(token=apikey) if PapersWithCodeClient and apikey else None

    #CRUXpider has three modes:
        #RW mode
        #getPaper mode
        #addPaper mode
        #See user manual
    
    
    #instantiate CRUXiper object
    parser = argparse.ArgumentParser(description= 'CRUXpider')
    parser.add_argument('--mode', choices = ['RW', 'getPaper', 'addPaper', 'relevantPaper', 'fullyAutomate'], help = "Choose Program Mode")
    
    if parser.parse_known_args()[0].mode == "RW":
        parser.add_argument('--input',help='Path to input file', required = True)
        parser.add_argument('--output', help="Path to output file", required = True)

    elif parser.parse_known_args()[0].mode == "getPaper":
        parser.add_argument('--From',help='Target Venue List', required = True)
        parser.add_argument('--num', help="number of Papers", required = True)
        parser.add_argument('--time', help="target time to start with", required= True)
        parser.add_argument('--output', help="Path to output file", required = True)
        
    elif parser.parse_known_args()[0].mode == "addPaper":
        parser.add_argument('--ToFile', help='Target File you append paper title to', required = True)
        parser.add_argument('--paperName', help ='The title of paper to be added',required=True)

    elif parser.parse_known_args()[0].mode == "relevantPaper":
        parser.add_argument('--input', help='Path to input file', required = True)
        parser.add_argument('--maxNum', help = 'the Max number of paper titles in a single file', required = True)
        parser.add_argument('--output', help='Path to output file', required = True)
    
    elif parser.parse_known_args()[0].mode == "fullyAutomate":
        parser.add_argument('--input', help='Path to input file', required = True)
        parser.add_argument('--maxNum', help = 'the Max number of paper titles in a single file', required = True)
        parser.add_argument('--output', help='Path to output file', required = True)


    
    args = parser.parse_args()
    
    if args.mode == 'RW':
        print("Running RW mode!")
        if args.input:
            inputfile = args.input
            PaperDF = parse_file(inputfile)
            xiper = CRUXiperRW(client, PaperDF)
            xiper.get_journal()
            xiper.get_PaperURL()
            xiper.get_Categories()
            xiper.get_PaperID()
            xiper.get_Dataset()
            xiper.get_Methods()
            xiper.get_repository()
            # xiper.get_repo_topics()
                
        if args.output:
            #assign a output path
            outputfile = args.output
            xiper.write_to_output(out_path = outputfile)

    elif args.mode == 'getPaper':
        print("Running getPaper mode!")
        if args.From:
            VenueName = args.From
        if args.num:
            PaperNum = args.num
        if args.output:
            Path = args.output
        if args.time:
            TargetTime = args.time
        xiper = CRUXpidergetPaper(Venue = VenueName,num = PaperNum, targetTime = TargetTime, targetPath = Path,)
        xiper.fromVenueGet()

    elif args.mode == 'addPaper':
        print("Add Success!")
        if args.ToFile:
            FileName = args.ToFile
        if args.paperName:
            # paperlist = [paper.replace(":","\\:").replace(" ", "\\ ") for paper in args.paperName.split(",")]
            paperlist = [paper for paper in args.paperName.split(",")]
        xiper = CRUXpideraddPaper(targetPath = FileName, paperList = paperlist)
        xiper.AddtoFile()

    elif args.mode == 'relevantPaper':
        print("Fetching Relevant Paper!")
        if args.input:
            inputfile = args.input
        if args.maxNum:
            maxNumber = args.maxNum
        if args.output:
            outputfile = args.output
        xiper = CRUXpiderRelevantPaper(inputFile = inputfile, maxNum = maxNumber, outputFile = outputfile)
        xiper.get_Relevant_Paper()

    elif args.mode == 'fullyAutomate':
        if args.input:
            inputfile = args.input
        if args.maxNum:
            maxNumber = args.maxNum
        if args.output:
            outputfile = args.output
        xiper = CRUXpiderRelevantPaper(inputFile = inputfile, maxNum = maxNumber, outputFile = outputfile)
        xiper.get_Relevant_Paper()
        inputfile = outputfile
        PaperDF = parse_file(inputfile)
        xiper = CRUXiperRW(client, PaperDF)
        xiper.get_journal()
        xiper.get_PaperURL()
        xiper.get_Categories()
        xiper.get_PaperID()
        xiper.get_Dataset()
        xiper.get_Methods()
        xiper.get_repository()
        xiper.write_to_output(out_path = outputfile)

        


if __name__ == '__main__':
    main()
