
%1. Read the nodes coordinate from ABAQUS
%a. Read 'Node_Data.txt' file.
    read_Node = fopen('Matrix.txt'); %modify the name of text file
    format_Node = '%f';
    size_Node = [3 Inf];   %modify the number of column
    Node_o = fscanf(read_Node,format_Node,size_Node);
    fclose(read_Node);
    Node_Data=Node_o';   
    
%b. Determine the Number of Nodes.
    Nodes=size(Node_Data,1);
        
%c. Update the Node_Data.
    X=Node_Data(:,1);
    Y=Node_Data(:,2); % Choose some parts of data, not all
    Z=Node_Data(:,3);
    
    A=Node_Data;

%Input

X1=-46; %the X coordinate of the first measuring
Y1=35.0400009; %the Y coordinate of the first measuring
X2=-51; %the X coordinate of the second measuring
Y2=30.0400009; %the Y coordinate of the second measuring
X23=-51; %The X coordinate of the middle point between point 2 and 3
Y23=0.709999979; %The Y coordinate of the middle point between point 2 and 3
X3=-51; %the X coordinate of the third measuring
Y3=-10.96; %the Y coordinate of the third measuring
X4=-40.8923073; %the X coordinate of the fourth measuring
Y4=-15.96; %the Y coordinate of the fourth measuring
X5=-0.030769231; %the X coordinate of the firth measuring
Y5=-15.96; %the Y coordinate of the firth measuring
X6=40.7999992; %the X coordinate of the six measuring
Y6=-15.96; %the Y coordinate of the six measuring
X7=51; %the X coordinate of the seventh measuring
Y7=-10.96; %the Y coordinate of the seventh measuring
X78=51; %The X coordinate of the middle point between point 7 and 8
Y78=0.709999979; %The Y coordinate of the middle point between point 7 and 8
X8=51;%the X coordinate of the eight measuring
Y8=30.0400009;%the Y coordinate of the eight measuring
X9=46;%the X coordinate of the nineth measuring
Y9=35.0400009;%the Y coordinate of the nineth measuring



L=	1500	;
n=	15337	;
G1=	1	;
T2=	0	;
T3=	0	;
T4=	0	;
T6=	0	;
T7=	0	;
T8=	0	;
		
D1=	-0.09035122	;
D2=	0.49392	;
D5=	0.14625	;
D8=	-0.49392	;
D9=	-0.09035122	;
D23=	0.132033249	;
D78=	-0.132033249	;
		
L5=	0.2925	;
L23=	-0.05	;
L78=	0.05	;
		
		
Nl=	19	;
Nd=	4	;
















%Incorporation code:

for i=1:n 
        if A(i,1)==X1 & A(i,2)==Y1 
        A(i,2)=A(i,2)+(	D1	)*sin(	Nd	*3.14*A(i,3)/L);
    end
end
    
for i=1:n 
    if A(i,1)==X2 & A(i,2)==Y2
        A(i,1)=A(i,1)+(	D2	)*sin(	Nd	*3.14*A(i,3)/L)+(	T2	)*sin(3.14*A(i,3)/L);
    end
end
     

for i=1:n 
    if A(i,1)==X23 & A(i,2)==Y23 
        A(i,1)=A(i,1)+(	D23	)*sin(	Nd	*3.14*A(i,3)/L)+(	L23	)*sin(	Nl	*3.14*A(i,3)/L);
    end
end   


for i=1:n 
    if A(i,1)==X3 & A(i,2)==Y3 
        A(i,1)=A(i,1)+(	T3	)*sin(3.14*A(i,3)/L);
    end
end    

for i=1:n 
    if A(i,1)==X4 & A(i,2)==Y4 
        A(i,2)=A(i,2)+(	G1+T4	)*sin(3.14*A(i,3)/L);
    end
end    

for i=1:n 
    if A(i,1)==X5 & A(i,2)==Y5 
        A(i,2)=A(i,2)+(	G1	)*sin(3.14*A(i,3)/L)+(	L5	)*sin(3.14*	Nl	*A(i,3)/L)+(D5)*sin(Nd*3.14*A(i,3)/L);
    end
end   

for i=1:n 
    if A(i,1)==X6 & A(i,2)==Y6 
        A(i,2)=A(i,2)+(	G1+T6	)*sin(3.14*A(i,3)/L);
    end
end 

for i=1:n 
    if A(i,1)==X7 & A(i,2)==Y7 
        A(i,1)=A(i,1)+(	T7	)*sin(3.14*A(i,3)/L);
    end
end 


for i=1:n 
    if A(i,1)==X78 & A(i,2)==Y78 
        A(i,1)=A(i,1)+(	D78	)*sin(	Nd	*3.14*A(i,3)/L)+(	L78	)*sin(	Nl	*3.14*A(i,3)/L);
    end
end  

%The eight measuring - F8
for i=1:n 
    if A(i,1)==X8 & A(i,2)==Y8 
        A(i,1)=A(i,1)+(	D8	)*sin(	Nd	*3.14*A(i,3)/L)+(	T8	)*sin(3.14*A(i,3)/L);
    end
end

for i=1:n 
    if A(i,1)==X9 & A(i,2)==Y9 
        A(i,2)=A(i,2)+(	D9	)*sin(	Nd	*3.14*A(i,3)/L);
    end
end


for i=1:n       
    if A(i,1)<0 & A(i,1)>X1 & A(i,2)>Y2 
        A(i,2)=A(i,2)+((	D1	)*sin(	Nd	*3.14*A(i,3)/L))*(A(i,1)-X2)/(X1-X2);
    end
end

for i=1:n       
    if A(i,1)<X1 & A(i,2)>Y2 
        A(i,2)=A(i,2)+((	D1	)*sin(	Nd	*3.14*A(i,3)/L))*(A(i,1)-X2)/(X1-X2);
    end
end


for i=1:n       
    if A(i,2)>Y23 & A(i,2)<Y2 & A(i,1)<0 
        A(i,1)=A(i,1)+(((	D23	)*sin(	Nd	*3.14*A(i,3)/L)+(	L23	)*sin(	Nl	*3.14*A(i,3)/L))*(A(i,2)-Y2)+((	D2	)*sin(	Nd	*3.14*A(i,3)/L)+(	T2	)*sin(3.14*A(i,3)/L))*(Y23-A(i,2)))/(Y23-Y2);
    end
end



for i=1:n       
    if A(i,2)>Y3 & A(i,2)<Y23 & A(i,1)<0 
        A(i,1)=A(i,1)+(((	T3	)*sin(3.14*A(i,3)/L))*(A(i,2)-Y23)+((	D23	)*sin(	Nd	*3.14*A(i,3)/L)+(	L23	)*sin(	Nl	*3.14*A(i,3)/L))*(Y3-A(i,2)))/(Y3-Y23);
    end
end


for i=1:n       
    if A(i,1)<X5 & A(i,1)>X4 & A(i,2)<0 
        A(i,2)=A(i,2)+(((	G1	)*sin(3.14*A(i,3)/L)+(	L5	)*sin(3.14*	Nl	*A(i,3)/L)+(D5)*sin(Nd*3.14*A(i,3)/L))*(A(i,1)-X4)+((	G1+T4	)*sin(3.14*A(i,3)/L))*(X5-A(i,1)))/(X5-X4);
    end
end

for i=1:n       
    if A(i,1)<X6 & A(i,1)>X5 & A(i,2)<0 
        A(i,2)=A(i,2)+(((	G1+T6	)*sin(3.14*A(i,3)/L))*(A(i,1)-X5)+((	G1	)*sin(3.14*A(i,3)/L)+(	L5	)*sin(3.14*	Nl	*A(i,3)/L)+(D5)*sin(Nd*3.14*A(i,3)/L))*(X6-A(i,1)))/(X6-X5);
    end
end


for i=1:n       
    if A(i,2)>Y7 & A(i,2)<Y78 & A(i,1)>0 
        A(i,1)=A(i,1)+(((	D78	)*sin(	Nd	*3.14*A(i,3)/L)+(	L78	)*sin(	Nl	*3.14*A(i,3)/L))*(A(i,2)-Y7)+((	T7	)*sin(3.14*A(i,3)/L))*(Y78-A(i,2)))/(Y78-Y7);
    end
end


for i=1:n       
    if A(i,2)>Y78 & A(i,2)<Y8 & A(i,1)>0 
        A(i,1)=A(i,1)+(((	D8	)*sin(	Nd	*3.14*A(i,3)/L)+(	T8	)*sin(3.14*A(i,3)/L))*(A(i,2)-Y78)+((	D78	)*sin(	Nd	*3.14*A(i,3)/L)+(	L78	)*sin(	Nl	*3.14*A(i,3)/L))*(Y8-A(i,2)))/(Y8-Y78);
    end
end


for i=1:n       
    if A(i,1)>0 & A(i,1)<X9 & A(i,2)>Y8 
        A(i,2)=A(i,2)+((	D9	)*sin(	Nd	*3.14*A(i,3)/L) )*(X8-A(i,1))/(X8-X9);
    end
end

for i=1:n       
    if A(i,1)>X9 & A(i,2)>Y8 
        A(i,2)=A(i,2)+((	D9	)*sin(	Nd	*3.14*A(i,3)/L))*(X8-A(i,1))/(X8-X9);
    end
end


for i=1:n       
    if A(i,2)>Y2 & A(i,1)<0 
        A(i,1)=A(i,1)+(((	T3	)*sin(3.14*A(i,3)/L))*(A(i,2)-Y2)+((	D2	)*sin(	Nd	*3.14*A(i,3)/L)+(	T2	)*sin(3.14*A(i,3)/L))*(Y3-A(i,2)))/(Y3-Y2);
    end
end



for i=1:n       
    if A(i,2)<Y3 & A(i,1)<X4 
        A(i,1)=A(i,1)+((((	T3	)*sin(3.14*A(i,3)/L))*(A(i,2)-Y2)+((	D2	)*sin(	Nd	*3.14*A(i,3)/L)+(	T2	)*sin(3.14*A(i,3)/L))*(Y3-A(i,2)))/(Y3-Y2))*(A(i,2)-Y4)/(Y3-Y4);
    end
end

for i=1:n       
    if (A(i,1)<X4)|(A(i,1)>=X4& A(i,1)<0& A(i,2)>0)
        A(i,2)=A(i,2)+(((	G1	)*sin(3.14*A(i,3)/L)+(	L5	)*sin(3.14*	Nl	*A(i,3)/L)+(D5)*sin(Nd*3.14*A(i,3)/L))*(A(i,1)-X4)+((	G1+T4	)*sin(3.14*A(i,3)/L))*(X5-A(i,1)))/(X5-X4);
    end
end



for i=1:n       
    if A(i,2)>Y8 & A(i,1)>0 
        A(i,1)=A(i,1)+(((	D8	)*sin(	Nd	*3.14*A(i,3)/L)+(	T8	)*sin(3.14*A(i,3)/L))*(A(i,2)-Y7)+((	T7	)*sin(3.14*A(i,3)/L))*(Y8-A(i,2)))/(Y8-Y7);
    end
end



for i=1:n       
    if A(i,2)<Y7& A(i,1)>X6 
         A(i,1)=A(i,1)+((((	D8	)*sin(	Nd	*3.14*A(i,3)/L)+(	T8	)*sin(3.14*A(i,3)/L))*(A(i,2)-Y7)+((	T7	)*sin(3.14*A(i,3)/L))*(Y8-A(i,2)))/(Y8-Y7))*(A(i,2)-Y6)/(Y7-Y6);
    end
end

for i=1:n       
    if (A(i,1)>X6)| (A(i,1)<=X6 & A(i,1)>0 & A(i,2)>0)
        A(i,2)=A(i,2)+(((	G1+T6	)*sin(3.14*A(i,3)/L))*(A(i,1)-X5)+((	G1	)*sin(3.14*A(i,3)/L)+(	L5	)*sin(3.14*	Nl	*A(i,3)/L)+(D5)*sin(Nd*3.14*A(i,3)/L))*(X6-A(i,1)))/(X6-X5);
    end
end



dlmwrite('myfile.txt',A, 'precision', '%.6f', 'newline', 'pc') 
disp(A);
